#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["lz4", "zstandard"]
# ///
"""
bg3_lsv.py -- lezen van Baldur's Gate 3 savegames zonder het spel te starten.

Twee lagen:
  * read_package(path)  -> LSPK-container (.lsv) uitpakken naar {naam: bytes}
  * LSF(data_or_path)   -> Larian LSF/LSOF binair formaat naar een boom van Node's

Getest op savegames van BG3 4.1.1 (LSPK v18, LSF v7).
Formaatdefinities afgeleid van Norbyte/lslib (LSFReader.cs, LSFCommon.cs).

Afhankelijkheden: pip install zstandard lz4
"""

import io
import struct
import uuid
import zlib

import lz4.block
import lz4.frame
import zstandard

# ---------------------------------------------------------------- compressie

NONE, ZLIB, LZ4, ZSTD = 0, 1, 2, 3


def _decompress(data, uncompressed_size, flags, chunked=False):
    """flags = het gecombineerde methode/level-byte dat Larian overal gebruikt."""
    method = flags & 0x0F
    if uncompressed_size == 0:
        return b""
    if method == NONE:
        return data
    if method == ZLIB:
        return zlib.decompress(data)
    if method == LZ4:
        # 'chunked' betekent bij Larian: een echt LZ4-frame in plaats van een los block
        if chunked:
            return lz4.frame.decompress(data)
        return lz4.block.decompress(data, uncompressed_size=uncompressed_size)
    if method == ZSTD:
        return zstandard.ZstdDecompressor().decompress(
            data, max_output_size=uncompressed_size
        )
    raise ValueError("onbekende compressiemethode %d" % method)


# ------------------------------------------------------- LSPK (.lsv, .pak)

def read_package(path, want=None):
    """
    Pak een LSPK-container uit. Geeft {bestandsnaam: bytes} terug.

    `want` is een functie die een bestandsnaam krijgt en True teruggeeft als je
    dat bestand nodig hebt. Alleen die worden uitgepakt. Dat is essentieel bij
    de grote spel-packages: Textures.pak is gigabytes, en die wil je niet in
    zijn geheel in het geheugen trekken om drie tekstbestanden te vinden.
    """
    with open(path, "rb") as fh:
        magic, version = struct.unpack("<4sI", fh.read(8))
        if magic != b"LSPK":
            raise ValueError("geen LSPK-bestand (magic=%r)" % magic)
        if version not in (15, 16, 18):
            raise ValueError("LSPK-versie %d wordt niet ondersteund" % version)

        filelist_offset, _filelist_size = struct.unpack("<QI", fh.read(12))
        _flags, _priority = struct.unpack("<BB", fh.read(2))
        fh.read(16)                       # md5
        (num_parts,) = struct.unpack("<H", fh.read(2))
        if num_parts != 1:
            raise ValueError("meerdelige packages worden niet ondersteund")

        fh.seek(filelist_offset)
        num_files, compressed_size = struct.unpack("<II", fh.read(8))
        # De bestandslijst zelf is altijd een los LZ4-block
        raw = lz4.block.decompress(fh.read(compressed_size),
                                   uncompressed_size=num_files * 272)

        entry_size = len(raw) // num_files
        files = {}
        for i in range(num_files):
            entry = raw[i * entry_size:(i + 1) * entry_size]
            name = entry[:256].split(b"\x00")[0].decode("utf-8")
            off_lo, off_hi, _part, flags, size_on_disk, uncompressed = struct.unpack(
                "<IHBBII", entry[256:272]
            )
            if want is not None and not want(name):
                continue
            fh.seek(off_lo | (off_hi << 32))
            blob = fh.read(size_on_disk)
            files[name] = blob if uncompressed == 0 else _decompress(
                blob, uncompressed, flags
            )
        return files


# ------------------------------------------------------------------- LSF

ATTRIBUTE_TYPES = {
    0: "None", 1: "Byte", 2: "Short", 3: "UShort", 4: "Int", 5: "UInt",
    6: "Float", 7: "Double", 8: "IVec2", 9: "IVec3", 10: "IVec4",
    11: "Vec2", 12: "Vec3", 13: "Vec4", 14: "Mat2", 15: "Mat3",
    16: "Mat3x4", 17: "Mat4x3", 18: "Mat4", 19: "Bool", 20: "String",
    21: "Path", 22: "FixedString", 23: "LSString", 24: "ULongLong",
    25: "ScratchBuffer", 26: "Long", 27: "Int8", 28: "TranslatedString",
    29: "WString", 30: "LSWString", 31: "UUID", 32: "Int64",
    33: "TranslatedFSString",
}
_STRINGS = {20, 21, 22, 23, 29, 30}
_SCALARS = {1: "<B", 2: "<h", 3: "<H", 4: "<i", 5: "<I", 6: "<f", 7: "<d",
            24: "<Q", 26: "<q", 27: "<b", 32: "<q"}


class Node:
    """Eén knoop uit een LSF-boom: naam, attributen, kinderen."""

    __slots__ = ("name", "attrs", "children", "parent")

    def __init__(self, name):
        self.name = name
        self.attrs = {}
        self.children = []
        self.parent = None

    def child(self, name):
        """Eerste kind met deze naam, of None."""
        for c in self.children:
            if c.name == name:
                return c
        return None

    def kids(self, name):
        """Alle kinderen met deze naam."""
        return [c for c in self.children if c.name == name]

    def path(self):
        parts, node = [], self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return " > ".join(reversed(parts))

    def __repr__(self):
        return "<Node %s attrs=%d kids=%d>" % (
            self.name, len(self.attrs), len(self.children)
        )


class LSF:
    """Leest een LSF/LSOF-bestand. Resultaat: .regions (dict van rootknopen)."""

    def __init__(self, source):
        data = source if isinstance(source, bytes) else open(source, "rb").read()
        self._s = io.BytesIO(data)
        self._header()
        self._names_table()
        self._node_table()
        self._attribute_table()
        self.values = self._section(self._v_disk, self._v_unc, chunked=True)
        self._build_tree()

    # -- header -----------------------------------------------------------

    def _u(self, fmt):
        return struct.unpack(fmt, self._s.read(struct.calcsize(fmt)))

    def _header(self):
        magic, self.version = self._u("<4sI")
        if magic != b"LSOF":
            raise ValueError("geen LSF-bestand (magic=%r)" % magic)
        # v5+ heeft een 64-bits engine-versie in plaats van 32-bits
        (self.engine_version,) = self._u("<q" if self.version >= 5 else "<i")
        if self.version >= 6:   # vanaf BG3 staat er ook een 'keys'-tabel in
            (self._s_unc, self._s_disk, self._k_unc, self._k_disk,
             self._n_unc, self._n_disk, self._a_unc, self._a_disk,
             self._v_unc, self._v_disk) = self._u("<10I")
        else:
            (self._s_unc, self._s_disk, self._n_unc, self._n_disk,
             self._a_unc, self._a_disk, self._v_unc, self._v_disk) = self._u("<8I")
            self._k_unc = self._k_disk = 0
        self.compression_flags, _u2, _u3, self.metadata_format = self._u("<BBHI")

    def _section(self, size_on_disk, uncompressed, chunked):
        if size_on_disk == 0:
            return self._s.read(uncompressed) if uncompressed else b""
        return _decompress(self._s.read(size_on_disk), uncompressed,
                           self.compression_flags,
                           chunked and self.version >= 2)

    # -- tabellen ---------------------------------------------------------

    def _names_table(self):
        buf = io.BytesIO(self._section(self._s_disk, self._s_unc, False))
        (buckets,) = struct.unpack("<I", buf.read(4))
        self.names = []
        for _ in range(buckets):
            (count,) = struct.unpack("<H", buf.read(2))
            bucket = []
            for _ in range(count):
                (length,) = struct.unpack("<H", buf.read(2))
                bucket.append(buf.read(length).decode("utf-8", "replace"))
            self.names.append(bucket)

    def _name(self, packed):
        return self.names[packed >> 16][packed & 0xFFFF]

    def _node_table(self):
        buf = self._section(self._n_disk, self._n_unc, True)
        long_nodes = self.version >= 3 and self.metadata_format == 1
        step = 16 if long_nodes else 12
        self.node_defs = []
        for off in range(0, len(buf) - step + 1, step):
            chunk = buf[off:off + step]
            if long_nodes:
                name, parent, _sibling, first_attr = struct.unpack("<Iiii", chunk)
            else:
                name, first_attr, parent = struct.unpack("<Iii", chunk)
            self.node_defs.append((name, parent, first_attr))

    def _attribute_table(self):
        buf = self._section(self._a_disk, self._a_unc, True)
        self.attr_defs = []
        if self.version >= 3 and self.metadata_format == 1:
            # V3: elk attribuut bevat zijn eigen offset en de volgende index
            for off in range(0, len(buf) - 15, 16):
                name, tl, nxt, data_off = struct.unpack("<IIiI", buf[off:off + 16])
                self.attr_defs.append([name, tl & 0x3F, tl >> 6, data_off, nxt])
        else:
            # V2: offsets zijn cumulatief, en de ketening moet gereconstrueerd
            last_of_node, data_off = [], 0
            for index, off in enumerate(range(0, len(buf) - 11, 12)):
                name, tl, node_index = struct.unpack("<IIi", buf[off:off + 12])
                self.attr_defs.append([name, tl & 0x3F, tl >> 6, data_off, -1])
                slot = node_index + 1
                if len(last_of_node) > slot:
                    if last_of_node[slot] != -1:
                        self.attr_defs[last_of_node[slot]][4] = index
                    last_of_node[slot] = index
                else:
                    last_of_node.extend([-1] * (slot - len(last_of_node)))
                    last_of_node.append(index)
                data_off += tl >> 6

    # -- waarden ----------------------------------------------------------

    def _value(self, type_id, pos, length):
        v = self.values
        if type_id in _STRINGS:
            return v[pos:pos + length].rstrip(b"\x00").decode("utf-8", "replace")
        if type_id in _SCALARS:
            return struct.unpack_from(_SCALARS[type_id], v, pos)[0]
        if type_id == 19:
            return v[pos] != 0
        if type_id == 31:
            return str(uuid.UUID(bytes_le=v[pos:pos + 16]))
        if type_id == 28:                       # TranslatedString: alleen handle
            version = struct.unpack_from("<H", v, pos)[0]
            hl = struct.unpack_from("<i", v, pos + 2)[0]
            handle = v[pos + 6:pos + 6 + hl].rstrip(b"\x00").decode("utf-8", "replace")
            return {"handle": handle, "version": version}
        if type_id in (8, 9, 10):
            n = type_id - 6
            return list(struct.unpack_from("<%di" % n, v, pos))
        if type_id in (11, 12, 13):
            n = type_id - 9
            return list(struct.unpack_from("<%df" % n, v, pos))
        if type_id == 25:
            return v[pos:pos + length]
        if type_id == 0:
            return None
        return {"_type": ATTRIBUTE_TYPES.get(type_id, str(type_id)),
                "_raw": v[pos:pos + length].hex()}

    def _build_tree(self):
        self.nodes, self.regions = [], {}
        for packed_name, parent, first_attr in self.node_defs:
            node = Node(self._name(packed_name))
            index = first_attr
            while index != -1:
                name, type_id, length, offset, nxt = self.attr_defs[index]
                node.attrs[self._name(name)] = self._value(type_id, offset, length)
                index = nxt
            self.nodes.append(node)
            if parent == -1:
                self.regions[node.name] = node
            else:
                node.parent = self.nodes[parent]
                self.nodes[parent].children.append(node)

    # -- gemak ------------------------------------------------------------

    def find(self, name):
        """Alle knopen met deze naam, waar ze ook in de boom zitten."""
        return [n for n in self.nodes if n.name == name]


if __name__ == "__main__":
    import sys

    files = read_package(sys.argv[1])
    for name, blob in files.items():
        line = "%-45s %9d bytes" % (name, len(blob))
        if blob[:4] == b"LSOF":
            lsf = LSF(blob)
            line += "  LSF v%d, %d knopen, regio's: %s" % (
                lsf.version, len(lsf.nodes), ", ".join(list(lsf.regions)[:6])
            )
        print(line)
