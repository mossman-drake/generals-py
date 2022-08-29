# generals-py

generals.io bot written in python

## Ideas for improvement
### Structure / Utility
- ~~Separate out solution from boilderplate / skeleton~~
	- ~~There's an object-oriented example of this [here](https://github.com/personalcomputer/generalsio) but I didn't like the extra implementation decisions and length of syntax the the OOP structure added.~~
		- ~~I'm not actually sure the best way to achieve this thought~~
- Joining custom lobbies with url parameters can be used to set game properties. (e.g. https://bot.generals.io/games/delta?speed=4&spectate=true willjoin, change the game speed to 4x and become a spectator). I wonder if this could be utilized to automatically change the game speed during testing.
- Still want better game state display
    - ~~scoreboard and turn counter~~
    - map display improvements
        - ~~easier to quickly identify cities / capitals~~
            - ~~potentially alternate between displaying symbols and army sizes / ownership coloring on these tiles?~~
        - improve readability once army sizes start topping 3 digits
            - maybe even just make print_width never decrease within a single game.
    - at some point it might be worth considering moving away from the terminal?
        - It appears from the readme of the [human.exe repo](https://github.com/EklipZgit/generals-bot) that he is using some sort of a non-terminal display. Could all or some of that be ported?
### Solutions
#### Endgame
- First huge thing that will improve the solution is to take a different strategy after the enemy has been found.
	1. Once the enemy has been spotted, path to the enemy tile (closest?) to my capital until enemy capital found
	2. Pathing over own territory to aggregate on the way to the touch points of enemy territory
	3. Aggregation prior to attacks
	4. Timing of attacks to take advantage of 25th turn land gains
- Once enemy capital is found, pour resources into their capital
	- Balance between agression and defense of own capital
		- Consider whether enemy has seen my capital
- Use heuristics to pivot between more aggressive vs defensive strategies
	- mobileArmies=armies-land gives a maximum bound for army size an opponent could have currently aggregated
		- This can be further constrained by:
			- the size of all enemy armies within our vision
			- mobileArmies in previous turns
				- every 25th turn this cap for mobileArmies will increase by |land|, but realistically, even if the enemy had all armies aggregated before this another |land| half-turns are required to aggragate this influx into a single army
			- Analysis of past enemy actions from the perspective of the scoreboard
				- e.g. If the enemy just took a city, this might be a terrific opportunity to attack
				- If they haven't been expanding or taking a city for a bit, they're likely aggragating in anticipation of exploring / attacking
#### Expansion / Exploration
- Be decisive about city capturing (either avoid or capture; no blindly pathing over them by chance)
	- I'm not sure the ideal strategy long-term
	- At current level of play I think more cities captured the better
		- Maybe with the exception of within the first ~50 turns
	- Also, if a city is encountered mid-navigation, clearing moves / replanning may be beneficial
- Consider using a short-term optimization algorthm for land expansion
	- This may not be very feasible for live gameplay
	- Even running non-live to get a sense for the best expansion strategies for the first ~100-150 turns might be beneficial
- Remember cities / Capitals that have been seen
  - Even if the enemy retakes the land so that it is no longer within vision, we don't need to lose that knowledge
#### Other
- I would like to be able to know the timing of events
    - Are we getting game_update exactly 0.5 seconds apart every time?
        - What's the variance?
    - How close can we send an attack move before the next game_update for it to be executed on that update?
        - Is this just a product of ping?
    - Mostly this would be useful info if / when we have intensive processing going on