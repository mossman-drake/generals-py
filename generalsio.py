import random
from string import ascii_letters
from time import time
from urllib.parse import quote
from socketIO_client import SocketIO, BaseNamespace

# Terrain Constants.
# Any tile with a nonnegative value is owned by the player corresponding to its value.
# For example, a tile with value 1 is owned by the player with playerIndex = 1.
class Tile(object):
    EMPTY = -1
    MOUNTAIN = -2
    UNKNOWN = -3
    UNKNOWN_OBSTACLE = -4 # Cities and Mountains show up as Obstacles in the fog of war.


class GameClientListener(object):
    def handle_game_update(self, terrain, armies, cities, generals, half_turns, scores):
        pass

    def handle_game_start(self, map_size, player_index, game_Start_data):
        pass

    def handle_game_over(self, won, replay_url):
        pass

    def handle_chat(self, username, message):
        pass


class GameClient(object):
    """
    A small SDK for the http://generals.io bot API.
    """
    SERVER_URL = 'https://bot.generals.io'
    REPLAY_URL_TEMPLATE = 'https://bot.generals.io/replays/%s'

    CUSTOM_GAME_START_DELAY = 5

    def __init__(self, game_id, user_id=None):
        self._sock = SocketIO(GameClient.SERVER_URL, Namespace=BaseNamespace)

        self._sock.on('connect', self._on_connect)
        self._sock.on('reconnect', self._on_reconnect)
        self._sock.on('disconnect', self._on_disconnect)

        self._sock.on('error_set_username', self._on_error_set_username)
        self._sock.on('game_won', self._on_game_won)
        self._sock.on('game_lost', self._on_game_lost)
        self._sock.on('game_start', self._on_game_start)
        self._sock.on('game_update', self._on_game_update)
        self._sock.on('chat_message', self._on_chat_message)

        if user_id == None:
            print('No user_id specified. Creating random user_id.')
            print('Joining as Anonymous.')
            user_id = random.choices(ascii_letters, k=16)
        self._user_id = user_id

        self.game_over = False
        self.game_started = False
        self._map = []
        self._cities = []

        self._listeners = []

    def __del__(self):
        pass
        # if self._in_game:
        #     self._leave_game()
        # else:
        #     self._sock.emit('cancel', '1v1')
        #     self._in_queue = False

    def set_username(self, username):
        self._sock.emit('set_username', self._user_id, username)

    def join_1v1_queue(self):
        self._sock.emit('join_1v1', self._user_id)
        print('Joined 1v1 queue')

    def join_ffa_queue(self):
        self._sock.emit('play', self._user_id)
        print('Joined ffa queue')

    def join_custom(self, game_id, force_start_delay=5):
        self._sock.emit('join_private', game_id, self._user_id)
        print('Joined custom game at http://bot.generals.io/games/' + quote(game_id))
        join_time = time()
        while not self.game_started:
            if time() - join_time > force_start_delay:
                self.set_force_start(game_id)
            self.wait(seconds=1)


    def set_force_start(self, game_id, set_on=True):
        self._sock.emit('set_force_start', game_id, set_on)

    def chat(self, message):
        self._sock.emit('chat_message', self._chat_room, message)

    def attack(self, start, end, half_move=False):
        self._sock.emit('attack', start, end, half_move)

    def clear_moves(self):
        self._sock.emit('clear_moves')

    def add_listener(self, listener):
        assert isinstance(listener, GameClientListener)
        self._listeners.append(listener)

    def wait(self, seconds=None):
        self._sock.wait(seconds)

    def _leave_game(self):
        self._sock.emit('leave_game')

    def _on_game_won(self, data, _):
        self.game_over = True
        for listener in self._listeners:
            listener.handle_game_over(won=True, replay_url=self._replay_url)
        self._leave_game()

    def _on_game_lost(self, data, _):
        self.game_over = True
        for listener in self._listeners:
            listener.handle_game_over(won=False, replay_url=self._replay_url)
        self._leave_game()

    def _on_error_set_username(error_message):
        if error_message:
            print('Error setting username:')
            print(error_message)
        else:
            print('Username successfully set!')

    def _on_game_start(self, data, _):
        """
        data ~= {
            'playerIndex': 0,
            'playerColors': [0, 1],
            'replay_id': 'Slxq8MkJj',
            'chat_room': 'game_1661048455813hE5pKeqEdFLsHnrZACqK',
            'usernames': [
                '[Bot] Dark Deltoid',
                '[Bot] Android'
            ],
            'teams': [1, 2],
            'game_type': 'custom',
            'swamps': [],
            'lights': []
        }
        """
        self.game_started = True
        self._is_first_update = True
        self._game_Start_data = data
        self._player_index = data['playerIndex']
        self._replay_url = GameClient.REPLAY_URL_TEMPLATE % data['replay_id']

    def _on_game_update(self, data, _):
        """
        data ~= {
            scores: [
                { 'total': 14, 'tiles': 7, 'i': 0, 'color': 0, 'dead': false },
                { 'total': 14, 'tiles': 5, 'i': 1, 'color': 1, 'dead': false }
            ],
            'turn': 27,
            'attackIndex': 0,
            'generals': [ -1, 203 ],
            'map_diff': [
                189, 1,   8, 18,  1,  1,
                264, 3,  -1, -1, -1, 17,
                1, 1, 116
            ],
            'cities_diff': [ 1 ]
        }
        """
        self._processing_update = True
        self._map = _patch(self._map, data['map_diff'])
        self._cities = _patch(self._cities, data['cities_diff'])

        if self._is_first_update:
            # The first 2 elements of map are the width and height
            self._map_size = self._map[:2]
            print(f'Map is {self._map_size[0]} wide by {self._map_size[1]} tall.')
            for listener in self._listeners:
                listener.handle_game_start(self._map_size, self._player_index, self._game_Start_data)
            self._is_first_update = False

        tile_count = self._map_size[0] * self._map_size[1]
        # The next |tile_count| terms are army values; armies[0] is the top-left corner of the map.
        armies = self._map[2:2 + tile_count]
        # The last |tile_count| terms are terrain values; terrain[0] is the top-left corner of the map.
        terrain = self._map[2 + tile_count:2 + tile_count*2]


        # After game over, we will get 1 update with all land visible and the winner owning all captured land
        # Don't run custom update logic on this.
        if not self.game_over:
            for listener in self._listeners:
                listener.handle_game_update(
                    terrain=terrain,
                    armies=armies,
                    cities=self._cities,
                    generals=data['generals'],
                    half_turns=data['turn'],
                    scores=data['scores']
                )

        self._processing_update = False

    def _on_chat_message(self, chat_queue, data):
        if 'username' in data:
            username = data['username']
        else:
            username = '[System]'
        for listener in self._listeners:
           listener.handle_chat(username, data['text'])

    def _on_connect(self):
        print('[Connected]')

    def _on_reconnect(self):
        print('[Reconnected]')

    def _on_disconnect(self):
        print('[Disconnected]')

def _patch(old, diff):
    '''
    Returns a new array created by patching the diff into the old array.
    The diff formatted with alternating matching and mismatching segments:
    <Number of matching elements>
    <Number of mismatching elements>
    <The mismatching elements>
    ... repeated until the end of diff.
    Example 1: patching a diff of [1, 1, 3] onto [0, 0] yields [0, 3].
    Example 2: patching a diff of [0, 1, 2, 1] onto [0, 0] yields [2, 0].
    '''
    out = []
    cursor = 0
    while cursor < len(diff):
        if diff[cursor]:  # matching
            out.extend(old[len(out): len(out) + diff[cursor]])
        cursor+=1
        if cursor < len(diff) and diff[cursor]:  # mismatching
            out.extend(diff[cursor + 1: cursor + 1 + diff[cursor]])
            cursor += diff[cursor]
        cursor+=1
    return out
