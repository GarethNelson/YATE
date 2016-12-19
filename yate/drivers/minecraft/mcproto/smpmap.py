"""
Taken from spockbot and modified, license is visible below:

 Copyright (C) 2015 The SpockBot Project

 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:

 The above copyright notice and this permission notice shall be included in
 all copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 THE SOFTWARE.


"""

import array
import struct
from math import floor

import buffer

DIMENSION_NETHER = -0x01
DIMENSION_OVERWORLD = 0x00
DIMENSION_END = 0x01


def mapshort2id(data):
    return data >> 4, data & 0x0F


class BlockEntityData(object):
    def __init__(self, nbt):
        self.nbt = nbt

    def __getattr__(self, key):
        return getattr(self.nbt, key)

    def __str__(self):
        return str(self.nbt)

    def __repr__(self):
        return repr(self.nbt)


class SpawnerData(BlockEntityData):
    pass  # TODO get entity class from mcdata?


class CommandBlockData(BlockEntityData):
    pass


class BeaconData(BlockEntityData):
    pass


class HeadData(BlockEntityData):
    pass


class FlowerPotData(BlockEntityData):
    def __init__(self, nbt):
        super(FlowerPotData, self).__init__(nbt)
        self.block = nbt['Item'].value, nbt['Data'].value
        # TODO get block instance from mcdata?


class BannerData(BlockEntityData):
    pass


class SignData(BlockEntityData):
    def __init__(self, line_data):
        super(SignData, self).__init__(self)
        self.lines = [line_data['line_%i' % (i + 1)] for i in range(4)]

    def __str__(self):
        return 'Sign%s' % str(self.lines)

    def __repr__(self):
        return '<SignData %s>' % repr(self.lines)


block_entities = {
    1: SpawnerData,
    2: CommandBlockData,
    3: BeaconData,
    4: HeadData,
    5: FlowerPotData,
    6: BannerData,
}


class ChunkData(object):
    length = 16 * 16 * 16
    ty = 'B'
    data = None

    def fill(self):
        if not self.data:
            self.data = array.array(self.ty, [0] * self.length)

    def unpack(self, buff):
        self.data = array.array(self.ty, buff.read(self.length))

    def pack(self):
        self.fill()
        return self.data.tobytes()

    def get(self, x, y, z):
        self.fill()
        return self.data[x + ((y * 16) + z) * 16]

    def set(self, x, y, z, data):
        self.fill()
        self.data[x + ((y * 16) + z) * 16] = data


class BiomeData(ChunkData):
    """ A 16x16 array stored in each ChunkColumn. """
    length = 16 * 16
    data = None

    def get(self, x, z):
        self.fill()
        return self.data[x + z * 16]

    def set(self, x, z, d):
        self.fill()
        self.data[x + z * 16] = d


class ChunkDataShort(ChunkData):
    """ A 16x16x16 array for storing block IDs and metadata. """
    length = 16 * 16 * 16 * 2
    ty = 'H'  # protocol allows larger block types

    def unpack(self, buff):
        _block_bits = buff.read(1)[0]
        block_bits = struct.unpack('>B',_block_bits)[0]
        uses_palette = block_bits > 0

        if uses_palette:
            palette_len = buff.unpack_varint()
            palette = [buff.unpack_varint() for i in range(palette_len)]
        else:  # use global palette
            block_bits = 13

        data_longs = buff.unpack_varint()
        block_data = [buff.unpack('Q')
                      for i in range(data_longs)]

        self.fill()
        blocks = self.data
        max_value = (1 << block_bits) - 1
        for i in range(4096):
            start_long = (i * block_bits) // 64
            start_offset = (i * block_bits) % 64
            end_long = ((i + 1) * block_bits - 1) // 64
            if end_long > 0:
               if start_long == end_long:
                   block = (block_data[start_long] >> start_offset) & max_value
               else:
                   end_offset = 64 - start_offset
                   block = (block_data[start_long] >> start_offset |
                            block_data[end_long] << end_offset) & max_value

               if uses_palette:  # convert to global palette
                   blocks[i] = palette[block]
               else:
                   blocks[i] = block

    def pack(self):
        raise NotImplementedError('1.9 block data packing not implemented')


class ChunkDataNibble(ChunkData):
    """ A 16x16x8 array for storing metadata, light or add. Each array element
    contains two 4-bit elements. """
    length = 16 * 16 * 8

    def get(self, x, y, z):
        self.fill()
        x, r = divmod(x, 2)
        i = x + ((y * 16) + z) * 16
        return self.data[i] & 0x0F if r else self.data[i] >> 4

    def set(self, x, y, z, data):
        self.fill()
        x, r = divmod(x, 2)
        i = x + ((y * 16) + z) * 16
        if r:
            self.data[i] = (self.data[i] & 0xF0) | (data & 0x0F)
        else:
            self.data[i] = (self.data[i] & 0x0F) | ((data & 0x0F) << 4)


class Chunk(object):
    def __init__(self):
        self.block_data = ChunkDataShort()
        self.light_block = ChunkDataNibble()
        self.light_sky = ChunkDataNibble()


class ChunkColumn(object):
    def __init__(self):
        self.chunks = [None] * 16
        self.biome = BiomeData()

    def unpack(self, buff, mask, skylight=True, continuous=True):
        # In the protocol, each section is packed sequentially (i.e. attributes
        # pertaining to the same chunk are *not* grouped)
        chunk_idx = [i for i in range(16) if mask & (1 << i)]
        for i in chunk_idx:
            if self.chunks[i] is None:
                self.chunks[i] = Chunk()
            self.chunks[i].block_data.unpack(buff)
        for i in chunk_idx:
            self.chunks[i].light_block.unpack(buff)
        if skylight:
            for i in chunk_idx:
                self.chunks[i].light_sky.unpack(buff)
        if continuous:
            self.biome.unpack(buff)


class Dimension(object):
    """ A bunch of ChunkColumns. """

    def __init__(self, dimension):
        self.dimension = dimension
        self.columns = {}  # chunk columns are address by a tuple (x, z)

        # BlockEntityData subclass instances, adressed by (x,y,z)
        self.block_entities = {}

    def unpack_bulk(self, data):
        
        bbuff = buffer.Buffer(data['data'])

        skylight = data['sky_light']
        for meta in data['metadata']:
            key = meta['chunk_x'], meta['chunk_z']
            if key not in self.columns:
                self.columns[key] = ChunkColumn()
            self.columns[key].unpack(bbuff, meta['primary_bitmap'], skylight)

    def unpack_column(self, data):
        bbuff = buffer.Buffer(data['data'])
        skylight = True if self.dimension == DIMENSION_OVERWORLD else False
        key = data['chunk_x'], data['chunk_z']
        if key not in self.columns:
            self.columns[key] = ChunkColumn()
        self.columns[key].unpack(
            bbuff, data['primary_bitmap'], skylight, data['continuous']
        )

    def get_block(self, pos_or_x, y=None, z=None):
        if None in (y, z):  # pos supplied
            pos_or_x, y, z = pos_or_x

        x, rx = divmod(int(floor(pos_or_x)), 16)
        y, ry = divmod(int(floor(y)), 16)
        z, rz = divmod(int(floor(z)), 16)
        if (x, z) not in self.columns or y > 0x0F:
            return 0, 0
        chunk = self.columns[(x, z)].chunks[y]
        if chunk is None:
            return 0, 0
        data = chunk.block_data.get(rx, ry, rz)
        return data >> 4, data & 0x0F

    def set_block(self, pos_or_x, y=None, z=None,
                  block_id=None, meta=None, data=None):
        if None in (y, z):  # pos supplied
            pos_or_x, y, z = pos_or_x

        x, rx = divmod(int(floor(pos_or_x)), 16)
        y, ry = divmod(int(floor(y)), 16)
        z, rz = divmod(int(floor(z)), 16)

        if y > 0x0F:
            return
        if (x, z) in self.columns:
            column = self.columns[(x, z)]
        else:
            column = ChunkColumn()
            self.columns[(x, z)] = column
        chunk = column.chunks[y]
        if chunk is None:
            chunk = Chunk()
            column.chunks[y] = chunk

        if data is None:
            data = (block_id << 4) | (meta & 0x0F)

        old_data = chunk.block_data.get(rx, ry, rz)
        chunk.block_data.set(rx, ry, rz, data)
        return old_data >> 4, old_data & 0x0F

    def get_block_entity_data(self, pos_or_x, y=None, z=None):
        """
        Access block entity data.

        Returns:
            BlockEntityData subclass instance or
            None if no block entity data is stored for that location.
        """
        if None not in (y, z):  # x y z supplied
            pos_or_x = pos_or_x, y, z
        coord_tuple = tuple(int(floor(c)) for c in pos_or_x)
        return self.block_entities.get(coord_tuple, None)

    def set_block_entity_data(self, pos_or_x, y=None, z=None, data=None):
        """
        Update block entity data.

        Returns:
            Old data if block entity data was already stored for that location,
            None otherwise.
        """
        if None not in (y, z):  # x y z supplied
            pos_or_x = pos_or_x, y, z
        coord_tuple = tuple(int(floor(c)) for c in pos_or_x)
        old_data = self.block_entities.get(coord_tuple, None)
        self.block_entities[coord_tuple] = data
        return old_data

    def get_light(self, pos_or_x, y=None, z=None):
        if None in (y, z):  # pos supplied
            pos_or_x, y, z = pos_or_x

        x, rx = divmod(int(floor(pos_or_x)), 16)
        y, ry = divmod(int(floor(y)), 16)
        z, rz = divmod(int(floor(z)), 16)

        if (x, z) not in self.columns or y > 0x0F:
            return 0, 0
        chunk = self.columns[(x, z)].chunks[y]
        if chunk is None:
            return 0, 0
        return chunk.light_block.get(rx, ry, rz), chunk.light_sky.get(rx, ry,
                                                                      rz)

    def set_light(self, pos_or_x, y=None, z=None,
                  light_block=None, light_sky=None):
        if None in (y, z):  # pos supplied
            pos_or_x, y, z = pos_or_x

        x, rx = divmod(int(floor(pos_or_x)), 16)
        y, ry = divmod(int(floor(y)), 16)
        z, rz = divmod(int(floor(z)), 16)

        if y > 0x0F:
            return
        if (x, z) in self.columns:
            column = self.columns[(x, z)]
        else:
            column = ChunkColumn()
            self.columns[(x, z)] = column
        chunk = column.chunks[y]
        if chunk is None:
            chunk = Chunk()
            column.chunks[y] = chunk

        if light_block is not None:
            chunk.light_block.set(rx, ry, rz, light_block & 0xF)
        if light_sky is not None:
            chunk.light_sky.set(rx, ry, rz, light_sky & 0xF)

    def get_biome(self, x, z):
        x, rx = divmod(int(floor(x)), 16)
        z, rz = divmod(int(floor(z)), 16)

        if (x, z) not in self.columns:
            return 0

        return self.columns[(x, z)].biome.get(rx, rz)

    def set_biome(self, x, z, data):
        x, rx = divmod(int(floor(x)), 16)
        z, rz = divmod(int(floor(z)), 16)

        if (x, z) in self.columns:
            column = self.columns[(x, z)]
        else:
            column = ChunkColumn()
            self.columns[(x, z)] = column

        return column.biome.set(rx, rz, data)