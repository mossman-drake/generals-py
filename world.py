from display import RESET_COLOR, NEUTRAL_CITY, player_color, rjust, print_as_grid

class World(object):
    def __init__(self, map_width, map_height, player_index, game_start_data):
        self.map_width = map_width
        self.map_height = map_height
        self.game_start_data = game_start_data
        self.player_index = player_index

        self.map = []
        self.terrain = None
        self.armies = None
        self.cities = None
        self.generals = None
        self.turn = None
        self.scores = None

    def update(self, terrain, armies, cities, generals, turn, scores):
        self.terrain = terrain
        self.armies = armies
        self.cities = cities
        self.generals = generals
        self.turn = turn
        self.scores = scores

    #   scores: [
    #     { total: 14, tiles: 7, i: 0, color: 0, dead: false },
    #     { total: 14, tiles: 5, i: 1, color: 1, dead: false }
    #   ],
    def scoreboard(self):
        usernames = self.game_start_data['usernames']
        scores_by_index = sorted(self.scores, key=lambda s: s['i'])
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

    def print_map(self, include_scores=True, include_turns= True):
        array = [self.armies[i] if tile >= 0 or i in self.cities else tile for i, tile in enumerate(self.terrain)]
        colored_tiles = {
            **{i: NEUTRAL_CITY for i in self.cities},
            **{i: player_color(tile, city=i in self.cities, capital=i in self.generals) for i, tile in enumerate(self.terrain) if tile >= 0}}
        battlefield = print_as_grid(array, self.map_width, colored_tiles=colored_tiles, print=False)
        map_components = [battlefield]
        if include_scores:
            map_components.insert(0, self.scoreboard())
        if include_turns:
            map_components.insert(0, 'Turn ' + str(self.turn//2)+('.' if self.turn%2 else ''))
        print('\n'.join(map_components))
