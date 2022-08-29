import random
import sys
import json

from generalsio import Tile, GameClient, GameClientListener
from world import World as BasicWorld


class World(BasicWorld):
    def __init__(self):
        super().__init__()
        self.capital_distances = None
        self.movement_finished_turn = 24

    def cardinal_translations(self):
        right = lambda start: None if start % self.map_width == self.map_width - 1 else start + 1
        left = lambda start: None if start % self.map_width == 0 else start - 1
        up = lambda start: None if start < self.map_width else start - self.map_width
        down = lambda start: None if start > self.map_width * (self.map_height - 1) - 1 else start + self.map_width
        return [right, up, left, down]


class Bot(GameClientListener, GameClient):
    def __init__(self, game_id, user_id):
        super().__init__(game_id, user_id)
        self.world = World()
        self.add_listener(self)

    def handle_game_start(self, map_size, player_index, game_start_data):
        self.world.map_width = map_size[0]
        self.world.map_height = map_size[1]
        self.world.player_index = player_index
        self.world.game_start_data = game_start_data

    def calculate_distances(self, reference_point):
        # print(f'calculate_distances({reference_point}); terrain:')
        # print_as_grid(terrain, width=map_width, tile_aliases={**DEFAULT_GRID_ALIASES, -5:'*'})
        # Improve: Make function to filter array by obstaces?
        distances = [Tile.UNKNOWN_OBSTACLE if t in (Tile.UNKNOWN_OBSTACLE, Tile.MOUNTAIN) else Tile.EMPTY for t in self.world.terrain]
        distances[reference_point] = 0; # 0 distance
        spots_to_check = [reference_point]
        while len(spots_to_check) > 0:
            current = spots_to_check.pop(0)
            for translation in self.world.cardinal_translations():
                new_spot = translation(current)
                if new_spot != None and distances[new_spot] == Tile.EMPTY:
                    distances[new_spot] = distances[current] + 1
                    spots_to_check.append(new_spot)
        return distances

    def chart_path(self, start, dest):
        # print(f'chart_path({start}, {dest})')
        dest_distances = self.calculate_distances(dest)
        # print('dest_distances:')
        # print_as_grid(dest_distances, width=map_width, tile_aliases={**DEFAULT_GRID_ALIASES, 0:'*'})
        path = [start]
        current = start
        while current != dest:
            # print(f'pathing over {current}')
            # Choose the step that results in the least remaining distance to destination
            next_step = [t(current) for t in self.world.cardinal_translations() if t(current) is not None and dest_distances[t(current)] !=Tile.UNKNOWN_OBSTACLE]
            next_step.sort(key=lambda a: dest_distances[a])
            next_step = next_step[0]
            path.append(next_step)
            current = next_step
        return path

    def traverse(self, start, end):
        # print(f'Traversal requested from {start} to {end}')
        if self.world.terrain[start] == self.world.player_index:
            path = self.chart_path(start, end)
            original_path = path
            if self.world.armies[start] < len(path):
                path = path[0: self.world.armies[start]]
                # IMPROVE: Possibly consider paths to pick up other troops on way?
                # print(f'Insufficient armies to travel from {start} to {end} ({len(original_path) - 1} tiles).' +
                #     f'Travelling {len(path) - 1} tiles to {path[-1]} instead.')
            # print(f'Moves queued: {path}')
            for i in range(len(path)-1):
                # print(f'queueing move: ${path[i]} to ${path[i+1]}')
                self.attack(path[i], path[i+1])
            return path
        else:
            print(f'traversal failed. terrain[{start}] = {self.world.terrain[start]} != {self.world.player_index}')
            # print_as_grid(terrain, width=map_width)

    def handle_game_update(self, terrain, armies, cities, generals, half_turns, scores):
        self.world.update(terrain, armies, cities, generals, half_turns, scores)
        # TODO: Remember cities
        # TODO: Remember general locations
        
    
        if not self.world.capital_distances:
            self.world.capital_distances = self.calculate_distances(self.world.generals[self.world.player_index])

        if self.world.turn >= self.world.movement_finished_turn:
            unowned_territory_distances = [-5 if terrain[i] == self.world.player_index else tile for i, tile in enumerate(self.world.capital_distances)]
            # print("unowned_territory_distances:")
            # print_as_grid(unowned_territory_distances, width=map_width, tile_aliases={**DEFAULT_GRID_ALIASES, -5:'*'})
            furthest_unexplored_loc = unowned_territory_distances.index(max(unowned_territory_distances))
            army_sizes = [army if terrain[i] == self.world.player_index else 0 for i, army in enumerate(armies)]
            largest_army_loc = army_sizes.index(max(army_sizes))
            path = self.traverse(largest_army_loc, furthest_unexplored_loc)
            # print('cities: ', cities)
            # print_path(path)
            self.world.movement_finished_turn = len(path) - 1 + self.world.turn

        self.world.print_map()

    def handle_game_over(self, won, replay_url):
        if won:
            header = 'Game Won'
        else:
            header = 'Game Lost'
        print(header)
        print('='*len(header))
        print('Replay: %s\n' % replay_url)

    def handle_chat(self, username, message):
        print('%s: %s' % (username, message))

    def wait_for_game_end(self):
        while not self.game_over:
            self.wait(seconds=2)


def main():
    game_id = None
    user_config =  None
    if len(sys.argv) > 1:
        game_id = sys.argv[1]
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

    while True:
        bot = Bot(game_id, user_config['user_id'])
        
        if game_id == '1v1':
            bot.join_1v1_queue()
        elif game_id == 'ffa':
            bot.join_ffa_queue()
        else:
            bot.join_custom(game_id, force_start_delay=5)

        bot.wait_for_game_end()


if __name__ == '__main__':
    main()