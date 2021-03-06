import pygame as pg
from ... import tools, prepare
from ...components.labels import Label, NeonButton
from .guts_player import GutsPlayer
from .guts_ai_player import AIPlayer
from .guts_game import GutsGame
from .guts_substates import Dealing, PlayerTurn, AITurn, ShowCards
from .guts_substates import ShowResults, Betting, StartGame, BankruptScreen

class Guts(tools._State):
    def __init__(self):
        super(Guts, self).__init__()
        self.screen_rect = pg.Rect((0,0), prepare.RENDER_SIZE)
        self.bet_amount = 10
        self.next = "LOBBYSCREEN"
        self.font = prepare.FONTS["Saniretro"]

    def startup(self, now, persistent):
        self.persist = persistent
        self.casino_player = self.persist["casino_player"]
        self.casino_player.current_game = "Guts"
        player_cash = self.casino_player.cash
        player_chips = None
        self.buttons = pg.sprite.Group()
        pos = (self.screen_rect.right - 320, self.screen_rect.bottom - 105)
        NeonButton(pos, "Lobby", self.back_to_lobby, None,
                          self.buttons, bindings=[pg.K_ESCAPE])
        self.player = GutsPlayer(player_cash, player_chips)
        self.ai_players = [AIPlayer("Player 1", "left", (160, 600)),
                                  AIPlayer("Player 2", "left", (160, 250)),
                                  AIPlayer("Player 3", "top", (455, 25)),
                                  AIPlayer("Player 4", "top", (755, 25)),
                                  AIPlayer("Player 5", "right", (1130, 250)),
                                  AIPlayer("Player 6", "right", (1130, 600))
                                  ]
        self.players = self.ai_players
        self.players.append(self.player)
        self.dealer_index = 2
        self.new_game()
        self.make_dynamic_labels()
        self.window = None
        
    def make_dynamic_labels(self):
        self.dynamic_labels = [
                    Label(self.font, 48, "Cash: ${}".format(self.player.cash), "gold3",
                            {"bottomleft": (10, 1040)})
                    ]

    def next_dealer(self):
        self.dealer_index += 1
        if self.dealer_index > len(self.players) - 1:
            self.dealer_index = 0

    def new_game(self, pot=None):
        if pot:
            pass
        elif self.player.cash < self.bet_amount:
            self.sub_state = BankruptScreen()
            return
        free_ride = True if pot else False
        pot = pot if pot else self.bet_amount * len(self.players)

        self.next_dealer()
        for player in self.players:
            player.cards = []
            player.stayed = False
            player.passed = False
            player.label = None
            player.won = 0
            player.lost = 0
        self.game = GutsGame(self.players, self.dealer_index, self.player,
                                           self.casino_player, self.bet_amount, pot, free_ride)
        if not self.game.free_ride:
            self.sub_states = [StartGame(self.game)]
        else:
            self.sub_states = []        
        self.sub_states.extend([Betting(self.game), Dealing(self.game)])
        for p in self.game.deal_queue:
            if p is self.player:
                self.sub_states.append(PlayerTurn(self.game, p))
            else:
                self.sub_states.append(AITurn(self.game, p))
        self.sub_states.append(ShowCards(self.game))
        self.sub_states.append(ShowResults(self.game))
        self.sub_states = iter(self.sub_states)
        self.sub_state = next(self.sub_states)

    def back_to_lobby(self, *args):
        self.persist["casino_player"].cash = self.player.cash
        self.next = "LOBBYSCREEN"
        self.done = True


    def get_event(self, event, scale):
        if event.type == pg.QUIT:
            self.back_to_lobby()
        for button in self.buttons:
            button.get_event(event)
        self.sub_state.get_event(event)
        if self.window:
            self.window.get_event(event)
        
    def update(self, surface, keys, current_time, dt, scale):
        if self.sub_state.done:
            try:
                self.sub_state = next(self.sub_states)
                self.sub_state.startup()
            except StopIteration:
                pot = sum([x.lost for x in self.players])
                self.player.cash -= self.player.lost
                self.casino_player.increase("total losses", self.player.lost)
                self.player.cash += self.player.won
                self.casino_player.increase("total winnings", self.player.won)
                if self.player.won:
                    self.casino_player.increase("hands won")
                if self.player.lost:
                    self.casino_player.increase("hands lost")                
                if pot:
                    self.new_game(pot)
                else:
                    self.new_game()
        self.sub_state.update(dt, scale)
        self.buttons.update(tools.scaled_mouse_pos(scale))
        self.make_dynamic_labels()

        self.sub_state.draw(surface)
        self.draw(surface)

    def draw(self, surface):
        #surface.fill(prepare.FELT_GREEN)
        #self.player.draw(surface)
        for button in self.buttons:
            button.draw(surface)
        for label in self.dynamic_labels:
            label.draw(surface)
        #self.dealer_button.draw(surface)