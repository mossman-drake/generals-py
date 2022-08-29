from wcwidth import wcswidth
import re

from generalsio import Tile

ANSII_FORMATTING_REGEX = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
def remove_formatting(text):
    return ANSII_FORMATTING_REGEX.sub('',text)

def rjust(text, length, padding=' '):
    return padding * max(0, (length - wcswidth(remove_formatting(text)))) + text

SHOGI_EMPTY = '☖'
SHOGI_FULL = '☗'
KING = '♔'
STAR_FULL = '★'
STAR_EMPTY = '☆'
SHINTO_SHRINE = '⛩'
SHADES = ' ░▒▓█'
ARROWS = '⇦⇧⇨⇩' + '←↑→↓' + '⏩⏪⏫⏬' + '⍗⍇⍐⍈'
MOUNTAIN = '⛰'
CASTLE = '🏰'
CROWN = '👑'
TENT = '⛺'
HUT = '🛖'

def color_code(text_color, background_color=None):
    r0,g0,b0 = text_color
    bgnd_str = '' if background_color is None else ';48;2;' + ';'.join([str(c) for c in background_color])
    return f'\x1b[38;2;{r0};{g0};{b0}{bgnd_str}m'

PLAYER_BASE_COLORS = [
    (255, 40, 40),  # Red
    (30, 100, 255), # Blue
    (0, 150, 0),    # Green
    (0, 170, 170),  # Sea-green
    (255, 130, 0),  # Orange
    (255, 70, 255), # Pink
    (100, 0, 100),  # Purple
    (120, 0, 0),    # Maroon
]
CAPITAL_BACKGROUND = (235, 235, 235)    # Mostly-White
CITY_BACKGROUND = (0, 0, 0)             # Black
RESET_COLOR = '\x1b[0m'
NEUTRAL_CITY = color_code((255, 255, 255), CITY_BACKGROUND)

def player_color(player_index, city=False, capital=False):
    return color_code(PLAYER_BASE_COLORS[player_index], CAPITAL_BACKGROUND if capital else CITY_BACKGROUND if city else None)

DEFAULT_GRID_ALIASES = {Tile.EMPTY: ' ', Tile.MOUNTAIN: MOUNTAIN+' ', Tile.UNKNOWN: SHADES[1]*2, Tile.UNKNOWN_OBSTACLE: MOUNTAIN+'?'}
def print_as_grid(array, width, print_axes=True, tile_aliases='default', colored_tiles=None, column_seperator = ' ', print=True):
    if len(array) % width != 0:
        print(f'Array of length {len(array)} is not rectangular with width of {width}.')
        return
    if tile_aliases == 'default':
        tile_aliases = DEFAULT_GRID_ALIASES
    if tile_aliases != None:
        # print(tile_aliases)
        array = [tile_aliases[tile] if tile in tile_aliases else str(tile) for tile in array]
    if colored_tiles != None:
        for tile in colored_tiles:
            array[tile] = (array[tile], colored_tiles[tile])
    if print_axes:
        array[0:0] = range(width) # Insert Horizontal axis labels at beginning of array
        for row_idx in range(len(array)//width-1, -1, -1): # Reverse to insert vertical axis labels
            array[row_idx*width:row_idx*width] = [' ' if row_idx == 0 else row_idx-1]
    print_width = max([wcswidth(str(tile[0] if type(tile) is tuple else tile)) for tile in array])
    color_wrap_if_tuple = lambda tile, contents: tile[1] + contents + RESET_COLOR if type(tile) is tuple else contents
    array = [color_wrap_if_tuple(tile, rjust(str(tile[0] if type(tile) is tuple else tile), print_width)) for tile in array]
    output = '\n'.join([column_seperator.join(array[row_idx*(width + (1 if print_axes else 0)):(row_idx+1)*(width + (1 if print_axes else 0))]) for row_idx in range(len(array)//(width + (1 if print_axes else 0)))])
    if print:
        print(output)
    return output

# directions = {'→': right, '←': left, '↑': up, '↓': down}
# def direction_of_move(move):
#     return [symbol for symbol, translation in  directions.items() if translation(move[0]) == move[1]][0]

# def print_path(path, grid=None):
#     if grid is None:
#         grid = terrain[:]
#     last_tile = path[0]
#     for tile in path[1:]:
#         correct_direction = direction_of_move((last_tile, tile))
#         grid[last_tile] = correct_direction
#         last_tile = tile
#     grid[generals[playerIndex]] = 314
#     print_as_grid(grid, colored_tiles={key: color_code((0, 0, 0), player_color(playerIndex)) for key in path}, column_seperator='')
