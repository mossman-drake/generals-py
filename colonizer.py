import random
from statistics import mean
import sys
import json
from time import time
import heapq
import csv

from display import print_as_grid
from generalsio import Tile, GameClient, GameClientListener
from world import World as BasicWorld

segment_times = {}
def time_segment(segment_name, start_time):
    global segment_times
    duration = time() - start_time
    if segment_name not in segment_times:
        segment_times[segment_name] = []
    segment_times[segment_name].append(duration)

def tot_times_sans_outliers():
    return {name: sum([time for time in times if time < 1]) for name, times in segment_times.items()}

class World(BasicWorld):
    def __init__(self, map_width, map_height, player_index, game_start_data):
        super().__init__(map_width, map_height, player_index, game_start_data)
        self.capital_distances = None
        self.movement_finished_turn = 24

    def cardinal_translations(self):
        right = lambda start: None if start % self.map_width == self.map_width - 1 else start + 1
        left = lambda start: None if start % self.map_width == 0 else start - 1
        up = lambda start: None if start < self.map_width else start - self.map_width
        down = lambda start: None if start > self.map_width * (self.map_height - 1) - 1 else start + self.map_width
        return [right, up, left, down]

    def update(self, terrain, armies, cities, generals, turn, scores):
        super().update(terrain, armies, cities, generals, turn, scores)
        # Improve: Only do this when new information warrants it (city found)
        self.capital_distances = self.calculate_distances(self.generals[self.player_index])

    def capital_location(self):
        return self.generals[self.player_index]

    def is_hostile_army(self, loc):
        return self.terrain[loc] != self.player_index and self.armies[loc] > 0

    def is_obstacle(self, loc):
        return self.terrain[loc] in (Tile.UNKNOWN_OBSTACLE, Tile.MOUNTAIN)

    def obstacle_view(self, obstacle_fn=None):
        if obstacle_fn is None:
            obstacle_fn = lambda i: self.is_obstacle(i)
        return [Tile.UNKNOWN_OBSTACLE if obstacle_fn(i) else Tile.EMPTY for i in range(len(self.terrain))]

    def calculate_distances(self, reference_point, obstacle_fn=None):
        # print(f'calculate_distances({reference_point}); terrain:')
        # print_as_grid(terrain, width=map_width, tile_aliases={**DEFAULT_GRID_ALIASES, -5:'*'})
        distances = self.obstacle_view(obstacle_fn)
        distances[reference_point] = 0; # 0 distance
        spots_to_check = [reference_point]
        while len(spots_to_check) > 0:
            current = spots_to_check.pop(0)
            for translation in self.cardinal_translations():
                new_spot = translation(current)
                if new_spot != None and distances[new_spot] == Tile.EMPTY:
                    distances[new_spot] = distances[current] + 1
                    spots_to_check.append(new_spot)
        return distances

    def chart_path(self, start, dest, obstacle_fn=None):
        dest_distances = self.calculate_distances(dest, obstacle_fn)
        # print('dest_distances:')
        # print_as_grid(dest_distances, width=map_width, tile_aliases={**DEFAULT_GRID_ALIASES, 0:'*'})
        path = [start]
        current = start
        while current != dest:
            # print(f'pathing over {current}')
            # Choose the step that results in the least remaining distance to destination
            next_step = [t(current) for t in self.cardinal_translations() if t(current) is not None and dest_distances[t(current)] != Tile.UNKNOWN_OBSTACLE]
            next_step.sort(key=lambda a: dest_distances[a])
            next_step = next_step[0]
            path.append(next_step)
            current = next_step
        return path

    def land_owned(self):
        return [self.coord_to_x_y(i) for i, tile in enumerate(self.terrain) if tile == self.player_index]

    def coord_to_x_y(self, coord):
        return (coord % self.map_width, coord // self.map_width)


class Bot(GameClientListener, GameClient):
    def __init__(self, game_id, user_id):
        super().__init__(game_id, user_id)
        self.add_listener(self)

    def handle_game_start(self, map_size, player_index, game_start_data):
        self.world = World(map_size[0], map_size[1], player_index, game_start_data)

    def traverse(self, start, end):
        # print(f'Traversal requested from {start} to {end}')
        if self.world.terrain[start] == self.world.player_index:
            obstacle_fn = lambda i: self.world.is_obstacle(i) or i in self.world.cities or (self.world.terrain[i] < 0 and self.world.armies[i] > 0)
            path = self.world.chart_path(start, end, obstacle_fn)
            original_path = path
            if self.world.armies[start] < len(path):
                # path = path[0: self.world.armies[start]]
                path = path[0:2]
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
        # update_start_time = time()
        self.world.update(terrain, armies, cities, generals, half_turns, scores)
        # TODO: Remember cities
        # TODO: Remember general locations

        if not hasattr(self.world, 'expansion_plan'):
            self.world.print_map()
            print(f'Turn {half_turns}: searching for optimal solution')
            self.world.expansion_plan = self.plan_optimal_moveset()
            print(self.world.expansion_plan)
            self.chat(str([clear['turn'] for clear in self.world.expansion_plan]))
        elif half_turns < 50:
            if len(self.world.expansion_plan) > 0:
                if half_turns//2 == self.world.expansion_plan[0]['turn']:
                    path = self.world.expansion_plan[0]['path']
                    for i in range(len(path)-1):
                        self.attack(path[i], path[i+1])
                    self.world.expansion_plan = self.world.expansion_plan[1:]
        else:
            del self._sock
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
        # self.world.print_map()


        # print(f'Time in update function: {round(time()-update_start_time,2)} seconds')

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

    def get_next_state(self, state, move):
        # start_time = time()
        board = state['board'][:]
        clears = [{**clear.copy(), 'path':clear['path'][:]} for clear in state['clears']]
        origin, destination = move
        if origin == self.world.capital_location():
            clears.append({
                'turn':clears[-1]['turn']-clears[-1]['gain'],
                'move_cap':clears[-1]['gain']*2,
                'gain':0, 'path':[]})
        clears[-1]['path'].append(destination)
        destination_value = board[destination]
        board[destination] = len(clears) - 1
        clears[-1]['gain'] += 1
        if destination_value != Tile.EMPTY:
            full_path = [item for sublist in [c['path'] for c in clears] for item in sublist]
            segment_lengths = [len(clear['path']) for clear in clears]
            segment_ends = [sum(segment_lengths[:i+1]) for i in range(len(segment_lengths))]
            previous_gain = None
            for i, clear in enumerate(clears):
                if i > 0:
                    clear['turn'] = clears[i-1]['turn'] - previous_gain
                    clear['move_cap'] = previous_gain * 2
                    clear['path'] = clear['path'][:clear['move_cap']]
                    # IMPROVE: If the last step in the path isn't a gain, shorten it?
                new_land = [step for step in clear['path'] if step not in full_path[segment_ends[i]:]]
                previous_gain = clear['gain'] = len(new_land)
                if clear['gain'] == 0 and (i < len(clears)-1 or len(clear['path']) == clear['move_cap']):
                    # time_segment('get_next_state', start_time)
                    return None
        # time_segment('get_next_state', start_time)
        return {'board': board, 'clears': clears}

    def possible_moves(self, state):
        # start_time = time()
        board = state['board']
        clears = state['clears']
        current_clear = clears[-1]
        moves = []
        # IMPROVE: Consider whether we may want to terminate a path early sometimes?
        capital = self.world.capital_location()
        origin = current_clear['path'][-1] if len(current_clear['path']) < current_clear['move_cap'] else capital
        for translation in self.world.cardinal_translations():
            destination = translation(origin)
            if destination is not None and \
                    board[destination] != Tile.UNKNOWN_OBSTACLE and \
                    (origin == capital or
                    (destination not in current_clear['path'] and destination != capital)):  # No pathing over this current path
                moves.append((origin, destination))
        # time_segment('possible_moves', start_time)
        return moves

    # Lower = better score
    def scored_state(state):
        return (-state['clears'][-1]['move_cap'] - random.random(), state)

    #  Save solutions to a csv for more analysis
    def save_solutions(self, board, solutions, file_name):
        with open(file_name, 'w') as csv_file:
            writer = csv.writer(csv_file)
            for soln in solutions:
                solution_row = []
                for clear in soln['clears']:
                    for step in clear['path']:
                        board[step] += 1
                        solution_row.append(str(step))
                    solution_row.append('stop')
                writer.writerow(solution_row)

            width = self.world.map_width
            writer.writerows([*['' for _ in range(3)], *[board[row_idx*width:(row_idx+1)*width] for row_idx in range(len(board)//width)]])

    def search_for_solution(self, final_clear):
        # IMPROVE: Consider allowing non-linear path (splitting with half-move)
        initial_state = {'board': self.world.obstacle_view(lambda i: self.world.is_obstacle(i) or self.world.is_hostile_army(i)),
                         'clears': [{'turn': 25, 'move_cap': 0, 'gain': 25-final_clear, 'path': []}]}
        remove_initial_clear = lambda state: {'board':state['board'], 'clears':state['clears'][1:]}
        queue = [Bot.scored_state(remove_initial_clear(self.get_next_state(initial_state, move))) for move in self.possible_moves(initial_state)] # array of tuples: [(board:array, turn:int, moves:array<tuple>), ...]
        heapq.heapify(queue)
        visited = {str(s[1]['clears']): True for s in queue}
        repeat_states = dead_states = 0
        isFullSoln = lambda state: state['clears'][-1]['gain'] >= state['clears'][-1]['turn']
        fullSolutions = []
        last_update = time()
        while len(queue) > 0:
            if time()-last_update > 5:
                print(f'len(queue):{len(queue)}, len(visited):{len(visited)}, len(fullSolutions):{len(fullSolutions)}, dead_states:{dead_states}, repeat_states:{repeat_states}')
                last_update = time()
            # start_time = time()
            current_state = heapq.heappop(queue)[1]
            # start_time1 = time()
            possible_next_moves = self.possible_moves(current_state)
            # time_segment('search_for_solution1', start_time1)
            for move in possible_next_moves:
                next_state = self.get_next_state(current_state, move)
                # start_time2 = time()
                if next_state is None:
                    dead_states += 1
                else:
                    if isFullSoln(next_state):
                        fullSolutions.append(next_state)
                        if len(fullSolutions)>1000:
                            queue = []
                    else:
                        if str(next_state['clears']) not in visited:
                            visited[str(next_state['clears'])] = True
                            heapq.heappush(queue, Bot.scored_state(next_state))
                        else:
                            repeat_states += 1
            #     time_segment('search_for_solution2', start_time2)
            # time_segment('search_for_solution', start_time)
        if len(fullSolutions):
            self.save_solutions(initial_state['board'], fullSolutions, './solutions/'+self._replay_url.split('/')[-1]+'.csv')
            return fullSolutions[0]
        else:
            print(f'Visited {len(visited)} states.\n' + f"Couldn't find way to own {final_clear+1} land by turn 25.")

    def plan_optimal_moveset(self):
        final_clear = 24
        solution = None
        while True:
            solution = self.search_for_solution(final_clear)
            if solution is not None:
                break
            # if len(solutions) > 0:
            #     return solutions
            final_clear -= 1
        capital = self.world.capital_location()
        return [{'turn': clear['turn'],
                 'path': [capital]+clear['path']}
                for clear in reversed(solution['clears'])]


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

    user_id = None if user_config is None else user_config['user_id']

    while True:
        bot = Bot(game_id, user_id)

        if game_id == '1v1':
            bot.join_1v1_queue()
        elif game_id == 'ffa':
            bot.join_ffa_queue()
        else:
            bot.join_custom(game_id, force_start_delay=2)
        try:
            bot.wait_for_game_end()
        except Exception as err:
            print(err)


if __name__ == '__main__':
    main()