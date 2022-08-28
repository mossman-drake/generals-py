import json
import sys
import random
from wcwidth import wcswidth
from turtle import color
from urllib.parse import quote
from string import ascii_letters
from socketIO_client import SocketIO, BaseNamespace
from time import time
import re

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

def ansii_code(text_color, background_color=None):
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
NEUTRAL_CITY = ansii_code((255, 255, 255), CITY_BACKGROUND)

def player_color(player_index, city=False, capital=False):
    return ansii_code(PLAYER_BASE_COLORS[player_index], CAPITAL_BACKGROUND if capital else CITY_BACKGROUND if city else None)


SERVER_URL = 'https://bot.generals.io'
REPLAY_URL_TEMPLATE = 'http://bot.generals.io/replays/%s'

def connect():
    global game_state, socket
    game_state = 'connecting'
    socket = SocketIO(SERVER_URL, Namespace=BaseNamespace) # What does Namespace do?
    socket.on('connect', handle_connect)
    # socket.on('reconnect', on_reconnect)
    socket.on('disconnect', handle_disconnect)
    socket.on('error_set_username', handle_set_username_error)
    socket.on('game_won', handle_win)
    socket.on('game_lost', handle_loss)
    socket.on('game_start', handle_game_start)
    socket.on('game_update', handle_game_update)
    # socket.on('chat_message', on_chat_message)

custom_game_id = None
user_config =  None
if len(sys.argv) > 1:
    custom_game_id = sys.argv[1]
else:
    raise ValueError('custom game id must be set as first command line argument')

if len(sys.argv) > 2:
    user_config_filename = sys.argv[2]
    try:
        with open(user_config_filename, "r") as user_config_file:
            user_config = json.load(user_config_file)
        if 'username' not in user_config:
            raise ValueError('custom user_configs must contain username')
        if 'user_id' not in user_config:
            raise ValueError('user_config must contain user_id')
        print(f'Using config {user_config_filename}.')
        print(f'Playing as {user_config["username"]}.')
    except:
        print(f'Error reading from user_config {user_config_filename}')
        user_config = None

if user_config == None:
    print('No user_config specified. Creating random user_id.')
    print('Joining as Anonymous.')
    user_config = {'user_id': random.choices(ascii_letters, k=16)}


game_state = 'disconnected'  # 'disconnected' | 'connecting' | 'connected' | 'lobby' | 'running'
processing_update = False


def handle_disconnect():
    global game_state
    print('Disconnected from server.')
    game_state = 'disconnected'

def handle_set_username_error(error_message):
    if error_message:
        print('Error setting username:')
        print(error_message)
    else:
        print('Username successfully set!')

def set_username_if_necessary():
    if 'username' in user_config and 'has_username_been_set' not in user_config:
        # Set the username for the bot.
        # This should only ever be done once. See the API reference for more details.
        socket.emit('set_username', user_config['user_id'], user_config['username'])

def join_lobby():
    global game_state, time_in_lobby
    game_state = 'lobby'
    time_in_lobby = time()

    if custom_game_id == '1v1':
        # Join the 1v1 queue.
        socket.emit('join_1v1', user_config['user_id'])
        print('Joined 1v1 queue')
    elif custom_game_id == 'ffa':
        # Join the FFA queue.
        socket.emit('play', user_config['user_id'])
        print('Joined ffa queue')
    else:
        # Join a custom game and force start immediately.
        # Custom games are a great way to test your bot while you develop it because you can play against your bot!
        socket.emit('join_private', custom_game_id, user_config['user_id'])
        # socket.emit('set_force_start', custom_game_id, True)
        print('Joined custom game at http://bot.generals.io/games/' + quote(custom_game_id))


    # Join a 2v2 team.
    # socket.emit('join_team', 'team_name', user_config['user_id']);

def handle_connect():
    global game_state
    print('Connected to server.')
    game_state = 'connected'


# Terrain Constants.
# Any tile with a nonnegative value is owned by the player corresponding to its value.
# For example, a tile with value 1 is owned by the player with playerIndex = 1.
class Tile(object):
    EMPTY = -1
    MOUNTAIN = -2
    UNKNOWN = -3
    UNKNOWN_OBSTACLE = -4 # Cities and Mountains show up as Obstacles in the fog of war.


def reset_globals():
    global playerIndex, generals, cities, terrain, armies, map, capital_distances, movement_finished_turn, game_start_data, scores, map_width, map_height, turn
    # Game data.
    playerIndex = None
    generals = None # The indicies of generals we have vision of.
    cities = [] # The indicies of cities we have vision of.
    terrain = None
    armies = None
    map = []
    capital_distances = None
    movement_finished_turn = 24
    game_start_data = None
    scores = None
    map_width = None
    map_height = None
    turn = None


# Returns a new array created by patching the diff into the old array.
# The diff formatted with alternating matching and mismatching segments:
# <Number of matching elements>
# <Number of mismatching elements>
# <The mismatching elements>
# ... repeated until the end of diff.
# Example 1: patching a diff of [1, 1, 3] onto [0, 0] yields [0, 3].
# Example 2: patching a diff of [0, 1, 2, 1] onto [0, 0] yields [2, 0].

def patch(old, diff):
    out = []
    i = 0
    while i < len(diff):
        if diff[i]:  # matching
            out.extend(old[len(out): len(out) + diff[i]])
        i+=1
        if i < len(diff) and diff[i]:  # mismatching
            out.extend(diff[i + 1: i + 1 + diff[i]])
            i += diff[i]
        i+=1
    return out


# {
#     'playerIndex': 0,
#     'playerColors': [0, 1],
#     'replay_id': 'Slxq8MkJj',
#     'chat_room': 'game_1661048455813hE5pKeqEdFLsHnrZACqK',
#     'usernames': [
#         '[Bot] Dark Deltoid',
#         '[Bot] Android'
#     ],
#     'teams': [1, 2],
#     'game_type': 'custom',
#     'swamps': [],
#     'lights': []
# }
def handle_game_start(data, _):
    global playerIndex, game_state, movement_finished_turn, capital_distances, game_start_data
    # Get ready to start playing the game.
    reset_globals()
    print(data)
    game_state = 'running'
    game_start_data = data
    playerIndex = data['playerIndex']
    # clearInterval(force_start_interval);
    replay_url = 'http://bot.generals.io/replays/' + quote(data['replay_id'])
    print('Game starting! The replay will be available after the game at ' + replay_url)
    print(f'I am player {playerIndex}')

def chart_path(start, dest):
    # print(f'chart_path({start}, {dest})')
    dest_distances = calculate_distances(dest)
    # print('dest_distances:')
    # print_as_grid(dest_distances, width=map_width, tile_aliases={**DEFAULT_GRID_ALIASES, 0:'*'})
    path = [start]
    current = start
    while current != dest:
        # print(f'pathing over {current}')
        # Choose the step that results in the least remaining distance to destination
        next_step = [t(current) for t in cardinal_translations if t(current) is not None and dest_distances[t(current)] !=Tile.UNKNOWN_OBSTACLE]
        next_step.sort(key=lambda a: dest_distances[a])
        next_step = next_step[0]
        path.append(next_step)
        current = next_step
    return path

right = lambda start: None if start % map_width == map_width - 1 else start + 1
left = lambda start: None if start % map_width == 0 else start - 1
up = lambda start: None if start < map_width else start - map_width
down = lambda start: None if start > map_width * (map_height - 1) - 1 else start + map_width
cardinal_translations = [right, up, left, down]

def calculate_distances(reference_point):
    # print(f'calculate_distances({reference_point}); terrain:')
    # print_as_grid(terrain, width=map_width, tile_aliases={**DEFAULT_GRID_ALIASES, -5:'*'})
    # Improve: Make function to filter array by obstaces?
    distances = [Tile.UNKNOWN_OBSTACLE if t in (Tile.UNKNOWN_OBSTACLE, Tile.MOUNTAIN) else Tile.EMPTY for t in terrain]
    distances[reference_point] = 0; # 0 distance
    spots_to_check = [reference_point]
    while len(spots_to_check) > 0:
        current = spots_to_check.pop(0)
        for translation in cardinal_translations:
            new_spot = translation(current)
            if new_spot != None and distances[new_spot] == Tile.EMPTY:
                distances[new_spot] = distances[current] + 1
                spots_to_check.append(new_spot)
    return distances


DEFAULT_GRID_ALIASES = {Tile.EMPTY: ' ', Tile.MOUNTAIN: MOUNTAIN+' ', Tile.UNKNOWN: SHADES[1]*2, Tile.UNKNOWN_OBSTACLE: MOUNTAIN+'?'}
def print_as_grid(array, width=None, print_axes=True, tile_aliases='default', colored_tiles=None, column_seperator = ' ', print=True):
    if width == None:
        width = map_width
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

#   scores: [
#     { total: 14, tiles: 7, i: 0, color: 0, dead: false },
#     { total: 14, tiles: 5, i: 1, color: 1, dead: false }
#   ],
def scoreboard():
    usernames = game_start_data['usernames']
    scores_by_index = sorted(scores, key=lambda s: s['i'])
    scoreboard_rows = [('Player', 'Army', 'Land'),
        *[(usernames[i],
        str(scores_by_index[i]['total']),
        str(scores_by_index[i]['tiles']))
        for i in range(len(usernames))]]
    column_widths = [max([len(str(row[col_idx])) for row in scoreboard_rows]) for col_idx in range(3)]
    stringified_scoreboard = '\n'.join([' '.join([
        (player_color(i-1) if i else '')+rjust(line[0],column_widths[0])+(RESET_COLOR if i else ''),
        rjust(line[1],column_widths[1]),
        rjust(line[2],column_widths[2])])
        for i, line in enumerate(scoreboard_rows)])
    return stringified_scoreboard

def print_map(include_turn_counter=True, include_scoreboard=True):
    array = [armies[i] if tile >= 0 or i in cities else tile for i, tile in enumerate(terrain)]
    colored_tiles = {
        **{i: NEUTRAL_CITY for i in cities},
        **{i: player_color(tile, city=i in cities, capital=i in generals) for i, tile in enumerate(terrain) if tile >= 0}}
    battlefield = print_as_grid(array, colored_tiles=colored_tiles, print=False)
    turn_string = 'Turn ' + str(turn//2)+('.' if turn%2 else '')
    print('\n'.join([turn_string, scoreboard(), battlefield]))

# This has some weaknesses:
# It will assume that the attack command got received before the next turn and therefore the traversal occurs.
def traverse(start, end):
    # print(f'Traversal requested from {start} to {end}')
    if terrain[start] == playerIndex:
        path = chart_path(start, end)
        original_path = path
        if armies[start] < len(path):
            path = path[0: armies[start]]
            # IMPROVE: Possibly consider paths to pick up other troops on way?
            # print(f'Insufficient armies to travel from {start} to {end} ({len(original_path) - 1} tiles).' +
            #     f'Travelling {len(path) - 1} tiles to {path[-1]} instead.')
        # print(f'Moves queued: {path}')
        for i in range(len(path)-1):
            # print(f'queueing move: ${path[i]} to ${path[i+1]}')
            socket.emit('attack', path[i], path[i+1])
        return path
    else:
        print(f'traversal failed. terrain[{start}] = {terrain[start]} != {playerIndex}')
        # print_as_grid(terrain, width=map_width)

directions = {'→': right, '←': left, '↑': up, '↓': down}
def direction_of_move(move):
    return [symbol for symbol, translation in  directions.items() if translation(move[0]) == move[1]][0]

def print_path(path, grid=None):
    if grid is None:
        grid = terrain[:]
    last_tile = path[0]
    for tile in path[1:]:
        correct_direction = direction_of_move((last_tile, tile))
        grid[last_tile] = correct_direction
        last_tile = tile
    grid[generals[playerIndex]] = 314
    print_as_grid(grid, colored_tiles={key: ansii_code((0, 0, 0), player_color(playerIndex)) for key in path}, column_seperator='')

# /**
#   scores: [
#     { total: 14, tiles: 7, i: 0, color: 0, dead: false },
#     { total: 14, tiles: 5, i: 1, color: 1, dead: false }
#   ],
#   turn: 27,
#   # IMPROVE: What is attackIndex? Does it give some information about past queued moves?
#   attackIndex: 0,
#   generals: [ -1, 203 ],
#   map_diff: [
#     189, 1,   8, 18,  1,  1,
#     264, 3,  -1, -1, -1, 17,
#       1, 1, 116
#   ],
#   cities_diff: [ 1 ]
#  */
def handle_game_update(data, _):
    global cities, map, generals, turn, map_width, map_height, armies, terrain, processing_update, scores
    processing_update = True
    scores = data['scores']
    # Patch the city and map diffs into our local variables.
    old_cities = cities
    cities = patch(cities, data['cities_diff'])
    cities = [c for c in set(old_cities) | set(cities)] # Remember cities that we've seen in the past

    map = patch(map, data['map_diff'])

    old_generals = generals
    generals = data['generals']
    if old_generals is not None:  # Remember if we've seen generals
        generals = [max(old_generals[i], general) for i, general in enumerate(generals)]

    turn = data['turn']

    # The first two terms in |map| are the dimensions.
    if map_width is None:
        print(f'Map is {map[0]} wide by {map[1]} tall.')

    map_width = map[0]
    map_height = map[1]
    size = map_width * map_height

    # The next |size| terms are army values.
    # armies[0] is the top-left corner of the map.
    armies = map[2: size + 2]

    # The last |size| terms are terrain values.
    # terrain[0] is the top-left corner of the map.
    terrain = map[size + 2: size + 2 + size]

    # After game over, we will get 1 update with all land visible and the winner owning all captured land
    # Don't run custom update logic on this.
    if game_state == 'running':
        custom_update_logic()

    processing_update = False

def custom_update_logic():
    global capital_distances, movement_finished_turn
    if not capital_distances:
        capital_distances = calculate_distances(generals[playerIndex])

    # if turn == 24:
    #     socket.emit('leave_game')
    #     print_map()
    #     optimal_plans = plan_optimal_moveset(land_plus_armies, 50)
    #     print('end')
    #     # end_state = optimal_plans[1][0][0]
    #     # print_as_grid(end_state)
    #     # print('moves:', optimal_plans[1][0][1])

    if turn >= movement_finished_turn:
        unowned_territory_distances = [-5 if terrain[i] == playerIndex else tile for i, tile in enumerate(capital_distances)]
        # print("unowned_territory_distances:")
        # print_as_grid(unowned_territory_distances, width=map_width, tile_aliases={**DEFAULT_GRID_ALIASES, -5:'*'})
        furthest_unexplored_loc = unowned_territory_distances.index(max(unowned_territory_distances))
        army_sizes = [army if terrain[i] == playerIndex else 0 for i, army in enumerate(armies)]
        largest_army_loc = army_sizes.index(max(army_sizes))
        path = traverse(largest_army_loc, furthest_unexplored_loc)
        # print('cities: ', cities)
        # print_path(path)
        movement_finished_turn = len(path) - 1 + turn

    print_map()


# Current state is a single-dimension array representing the board
# global map_width shows where to split rows
# All board is to be either Tile.EMPTY, Tile.UNKNOWN_OBSTACLE, or a non-negative army value
# cities is a list of indices for cities already owned
# This iteration will not work for capturing cities.
# Unowned cities are expected to be Tile.UNKNOWN_OBSTACLE and will be avoided
# move is either None (no movement) or a tuple of indices representing (start, finish)
# turn is the technically "half-turn" count from game_update (used for growing land)
def next_state(board, turn, owned_cities, move, half=False):
    if len(board) % map_width != 0:
        print(f'next_state: Array of length {len(board)} is not rectangular with width of {map_width}.')
        return
    if not all([t >= 0 or t in [Tile.EMPTY, Tile.UNKNOWN_OBSTACLE] for t in board]):
        print(f'next_state: Board has illegal values.')
    if not all([board[city] >= 0 for city in owned_cities]):
        print(f'City tiles must be owned')
    if move is not None:
        if not board[move[0]] >= 0:
            print('Must move from an owned tile')
        if not (board[move[1]] >= 0 or board[move[1]] == Tile.EMPTY):
            print('Must move to an empty or owned tile')
    board = board[:] # Copy
    if move is not None:
        board[move[1]] = board[move[0]] - 1 + max(board[move[1]], 0)
        board[move[0]] = 1
    if turn % 2 == 1: # Next turn is even (Or a non half-turn)
        for city in owned_cities:
            board[city] += 1
    if turn % 50 == 49: # Next turn is a 25th turn
        board = [tile + (1 if tile >= 0 else 0) for tile in board]
    return (board, turn+1)

def possible_moves(board, include_half_moves=False):
    mobile_armies = [i for i, tile in enumerate(board) if tile >= 2]
    moves = []
    for start in mobile_armies:
        for move in cardinal_translations:
            end = move(start)
            if end is not None and board[end] != Tile.UNKNOWN_OBSTACLE:
                moves.append((start, end))
    return moves

def land_plus_armies(board):
    armies = [tile for tile in board if tile >=0]
    return len(armies) + sum(armies)

def plan_optimal_moveset(scoring_function, final_turn):
    board = [armies[i] if tile >= 0 else
             Tile.UNKNOWN_OBSTACLE if i in cities or tile == Tile.MOUNTAIN else
             Tile.EMPTY if tile == Tile.UNKNOWN else tile
             for i, tile in enumerate(terrain)]
    owned_cities = [*[c for c in cities if board[c] >= 0], generals[playerIndex]]
    queue = [(board, turn, [])] # array of tuples: [(board:array, turn:int, moves:array<tuple>), ...]
    visited = [] # array of tuples: [(board, turn), ...]
    optimal_plans = {} # keys of turn numbers; values are (score, [(board:array, moves:array<tuple>), ...])
    while len(queue) > 0:
        board, game_turn, moves = queue.pop(0)
        visited.append((board, game_turn))
        score = scoring_function(board)
        if game_turn not in optimal_plans:
            optimal_plans[game_turn] = {}
        if score not in optimal_plans[game_turn]:
            optimal_plans[game_turn][score] = []
        optimal_plans[game_turn][score].append((land_owned(board),
            [(coord_to_x_y(move[0]), direction_of_move(move)) for move in moves]))
        # if game_turn not in optimal_plans or score > optimal_plans[game_turn][0]: # Best (and maybe first) for this turn
        #     optimal_plans[game_turn] = (score, [(board, moves)])
        # if score == optimal_plans[game_turn][0]: # Tied for best scoring moveset at this turn
        #     optimal_plans[game_turn][1].append((board, moves))
        if game_turn == final_turn:
            continue # No need to look at moves after final_turn
        possible_next_moves = possible_moves(board)
        if len(possible_next_moves) == 0:
            possible_next_moves = [None]
        for move in possible_next_moves:
            if move is not None and (move[1], move[0]) in moves: # No reverse moves
                continue
            state = next_state(board, game_turn, owned_cities, move)
            if state not in visited:
                queue.append(state+([*moves, move],))
    return optimal_plans

def land_owned(board):
    return [coord_to_x_y(i) for i, tile in enumerate(board) if tile >= 0]

def coord_to_x_y(coord):
    return (coord % map_width, coord // map_width)

def game_over():
    global game_state
    socket.emit('leave_game')
    game_state = 'connected'

def handle_win(_, __=None):
    print('I won!')
    game_over()

def handle_loss(_, __=None):
    print('I lose.')
    game_over()

while True:
    if game_state == 'disconnected':
        connect()
    elif game_state not in ['connecting', 'running'] and not processing_update:
        if game_state != 'lobby':
            join_lobby()
        if custom_game_id not in ['ffa', '1v1']:
            if time() - time_in_lobby > 4:
                socket.emit('set_force_start', custom_game_id, True)
    socket.wait(1)
