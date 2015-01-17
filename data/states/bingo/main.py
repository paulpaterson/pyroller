"""Main bingo game state"""

import time
import sys
import random
import pygame as pg
from collections import OrderedDict

from ... import tools, prepare
from ...components.labels import NeonButton
from ...components import common
from ...prepare import BROADCASTER as B

from . import statemachine
from . import states
from . import playercard
from . import dealercard
from . import patterns
from . import ballmachine
from . import cardselector
from . import events
from . import bingocard
from . import moneydisplay
from .settings import SETTINGS as S


class Bingo(statemachine.StateMachine):
    """State to represent a bing game"""

    def __init__(self):
        """Initialise the bingo game"""
        #
        self.verbose = False
        self.sound_muted = prepare.ARGS['debug']
        #
        self.screen_rect = pg.Rect((0, 0), prepare.RENDER_SIZE)
        self.auto_pick = S['debug-auto-pick']
        #
        self.ui = common.ClickableGroup()
        #
        self.lobby_button = NeonButton(S['lobby-position'], 'Lobby', self.return_to_lobby)
        self.new_game_button = NeonButton(S['new-game-position'], 'New', lambda x: self.restart_game(None, None))
        #
        # The controls to allow selection of different numbers of cards
        self.card_selector = cardselector.CardSelector('card-selector', self)
        self.card_selector.linkEvent(events.E_NUM_CARDS_CHANGED, self.change_number_of_cards)
        self.ui.append(self.card_selector.ui)
        #
        self.create_card_collection()
        self.ui.extend(self.cards)
        #
        self.winning_pattern = patterns.PATTERNS[0]
        #
        self.pattern_buttons = common.DrawableGroup()
        self.debug_buttons = common.pg.sprite.LayeredDirty()
        self.buttons = common.pg.sprite.LayeredDirty()
        #
        if prepare.DEBUG:
            self.buttons.add(self.debug_buttons)
        #
        super(Bingo, self).__init__()
        #
        # The machine for picking balls
        self.ball_machine = ballmachine.BallMachine('ball-machine', self)
        self.ball_machine.start_machine()
        self.ui.append(self.ball_machine.buttons)
        #
        self.all_cards = common.pg.sprite.LayeredDirty()
        for item in self.cards:
            self.all_cards.add(item)
        for item in self.dealer_cards:
            self.all_cards.add(item)
        #
        B.linkEvent(events.E_PLAYER_PICKED, self.player_picked)
        B.linkEvent(events.E_PLAYER_UNPICKED, self.player_unpicked)
        B.linkEvent(events.E_CARD_COMPLETE, self.card_completed)
        #
        self.current_pick_sound = 0
        self.last_pick_time = 0

    def startup(self, current_time, persistent):
        """This method will be called each time the state resumes."""
        self.persist = persistent
        self.casino_player = self.persist["casino_player"]
        #
        # Make sure the player has stat markers
        if 'Bingo' not in self.casino_player.stats:
            self.casino_player.stats['Bingo'] = OrderedDict([
                ('games played', 0),
                ('games won', 0),
                ('_last squares', []),
                ])
        #
        self.casino_player.stats['Bingo']['games played'] += 1
        self.cards.set_card_numbers(self.casino_player.stats['Bingo'].get('_last squares', []))
        self.money_display.set_money(self.casino_player.stats['cash'])

    def get_event(self, event, scale=(1,1)):
        """Check for events"""
        super(Bingo, self).get_event(event, scale)
        self.lobby_button.get_event(event)
        self.new_game_button.get_event(event)
        #
        if event.type == pg.QUIT:
            if prepare.ARGS['straight']:
                pg.quit()
                sys.exit()
            else:
                self.done = True
                self.next = "LOBBYSCREEN"
        elif event.type in (pg.MOUSEBUTTONDOWN, pg.MOUSEMOTION):
            #
            self.ui.process_events(event, scale)
            #
            pos = tools.scaled_mouse_pos(scale, event.pos)
        elif event.type == pg.KEYUP:
            if event.key == pg.K_ESCAPE:
                self.done = True
                self.next = "LOBBYSCREEN"
            elif event.key == pg.K_SPACE:
                self.next_chip(None, None)
            elif event.key == pg.K_m:
                #self.persist["music_handler"].mute_unmute_music()
                self.sound_muted = not self.sound_muted
            elif event.key == pg.K_f:
                for card in self.cards:
                    self.add_generator('flash-labels', card.flash_labels())

    def return_to_lobby(self, arg):
        """Return to the lobby screen"""
        self.game_started = False
        self.done = True
        self.next = "LOBBYSCREEN"
        self.casino_player.stats['Bingo']['_last squares'] = self.cards.get_card_numbers()
        self.casino_player.stats['cash'] = self.money_display.amount

    def drawUI(self, surface, scale):
        """Update the main surface once per frame"""
        mouse_pos = tools.scaled_mouse_pos(scale, pg.mouse.get_pos())
        self.lobby_button.update(mouse_pos)
        self.new_game_button.update(mouse_pos)
        #
        # surface.fill(S['table-color'])
        #
        self.lobby_button.draw(surface)
        self.new_game_button.draw(surface)
        # self.all_cards.draw(surface)
        # self.ball_machine.draw(surface)
        self.buttons.draw(surface)
        self.card_selector.draw(surface)
        # self.money_display.draw(surface)
        #

    def initUI(self):
        """Initialise the UI display"""
        #
        # Buttons that show the winning patterns
        x, y = S['winning-pattern-position']
        for idx, pattern in enumerate(patterns.PATTERNS):
            dx, dy = S['winning-pattern-buttons'][pattern.name]
            new_button = patterns.PatternButton(
                idx, (x + dx, y + dy),
                'bingo-wide-red-button', 'bingo-wide-red-button-off', 'winning-pattern',
                pattern.name,
                pattern == self.winning_pattern, S,
                scale=S['winning-pattern-scale']
            )
            new_button.linkEvent(common.E_MOUSE_CLICK, self.change_pattern, pattern)
            new_button.pattern = pattern
            self.pattern_buttons.add_original(new_button)
            self.buttons.add(new_button)
            self.ui.append(new_button)
        #
        # Simple generator to flash the potentially winning squares
        self.add_generator('potential-winners', self.flash_potential_winners())
        #
        # Display of the money the player has
        self.money_display = moneydisplay.MoneyDisplay(
            'money-display', S['money-position'], 0, self
        )
        prepare.BROADCASTER.linkEvent(events.E_SPEND_MONEY, self.spend_money)
        #
        # Button for next chip
        self.next_chip_button = common.ImageOnOffButton(
                'next-chip', S['next-chip-position'],
                'bingo-next-chip-on', 'bingo-next-chip-off', 'next-chip',
                'Next Chip (SPC)', True,
                S, scale=S['next-chip-scale']
        )
        self.next_chip_button.linkEvent(common.E_MOUSE_CLICK, self.next_chip)
        self.ui.append(self.next_chip_button)
        self.buttons.add(self.next_chip_button)
        #
        # Menu bar
        self.menu_bar = common.NamedSprite(
            'bingo-menu-bar', S['menu-bar-position'], scale=S['menu-bar-scale']
        )
        self.buttons.add(self.menu_bar)
        #
        # Debugging buttons
        if prepare.DEBUG and S['show-debug-buttons']:
            self.debug_buttons.add(common.ImageOnOffButton(
                'auto-pick', S['debug-auto-pick-position'],
                'bingo-yellow-button', 'bingo-yellow-off-button', 'small-button',
                'Auto pick',
                S['debug-auto-pick'],
                S, scale=S['small-button-scale']
            ))
            self.debug_buttons[-1].linkEvent(common.E_MOUSE_CLICK, self.toggle_auto_pick)
            #
            self.debug_buttons.add(common.ImageButton(
                'restart', S['debug-restart-position'],
                'bingo-yellow-button', 'small-button',
                'Restart',
                S, scale=S['small-button-scale']
            ))
            self.debug_buttons[-1].linkEvent(common.E_MOUSE_CLICK, self.restart_game)
            #
            self.debug_buttons.add(common.ImageButton(
                'next-ball', S['debug-next-ball-position'],
                'bingo-yellow-button', 'small-button',
                'Next Ball',
                S, scale=S['small-button-scale']
            ))
            self.debug_buttons[-1].linkEvent(common.E_MOUSE_CLICK, self.next_ball)
            #
            self.debug_buttons.add(common.ImageButton(
                'new-cards', S['debug-new-cards-position'],
                'bingo-yellow-button', 'small-button',
                'New Cards',
                S, scale=S['small-button-scale']
            ))
            self.debug_buttons[-1].linkEvent(common.E_MOUSE_CLICK, self.draw_new_cards)
            self.ui.extend(self.debug_buttons)

    def spend_money(self, amount, arg):
        """Money has been spent"""
        self.log.info('Money has been spent {1} by {0}'.format(arg, amount))
        self.money_display.add_money(amount)
        if amount < 0:
            self.play_sound('bingo-pay-money')

    def change_pattern(self, obj, pattern):
        """Change the winning pattern"""
        self.log.info('Changing pattern to {0}'.format(pattern.name))
        #
        # Account for the random factor
        if pattern.name == "Random":
            self.add_generator(
                'randomize-buttons',
                self.randomly_highlight_buttons(
                    self.pattern_buttons.original_objects[-1],
                    self.pattern_buttons.original_objects[:-1],
                    S['randomize-button-number'], S['randomize-button-delay'],
                    lambda b: self.change_pattern(None, b.pattern)
                )
            )
            return
        #
        self.winning_pattern = pattern
        self.highlight_patterns(self.winning_pattern, one_shot=True)
        #
        # Clear all flashing squares
        for card in self.all_cards:
            card.potential_winning_squares = []
            for square in card.squares.sprites():
                square.is_focused = False
        #
        # Update UI
        for button in self.pattern_buttons.original_objects:
            button.state = (button.pattern == self.winning_pattern)

    def toggle_auto_pick(self, obj, arg):
        """Toggle whether we are auto-picking numbers"""
        self.log.debug('Toggling auto-pick')
        self.auto_pick = not self.auto_pick
        self.debug_buttons[0].state = self.auto_pick

    def restart_game(self, obj, arg):
        """Restart the game"""
        self.log.info('Restart game')
        self.ball_machine.reset_machine(self.ball_machine.interval)
        self.cards.reset()
        self.dealer_cards.reset()
        self.current_pick_sound = 0
        self.last_pick_time = 0

    def next_ball(self, obj, arg):
        """Move on to the next ball

        This is a debugging method - no using the normal UI

        """
        self.ball_machine.call_next_ball()

    def next_chip(self, obj, arg):
        """Move on to the next ball"""
        if self.next_chip_button.state:
            self.ball_machine.call_next_ball()
            self.add_generator('next-chip-animation', self.animate_next_chip())

    def animate_next_chip(self):
        """Animate the button after choosing another chip"""
        self.next_chip_button.state = False
        yield S['next-chip-delay'] * 1000
        self.next_chip_button.state = True

    def draw_new_cards(self, obj,  arg):
        """Draw a new set of cards"""
        self.log.debug('Drawing new set of cards')
        self.cards.draw_new_numbers()
        self.cards.reset()

    def create_card_collection(self):
        """Return a new card collection"""
        number = self.card_selector.number_of_cards
        self.cards = playercard.PlayerCardCollection(
            'player-card',
            S['player-cards-position'],
            S['player-card-offsets'][number],
            self
        )
        dx, dy = S['dealer-card-offset']
        dealer_offsets = [(dx + x, dy +y) for x, y in S['player-card-offsets'][number]]
        self.dealer_cards = dealercard.DealerCardCollection(
            'dealer-card',
            S['player-cards-position'],
            dealer_offsets,
            self
        )

    def change_number_of_cards(self, number, arg=None):
        """Change the number of cards in play"""
        self.log.info('Changing the number of cards to {0}'.format(number))
        #
        # Store off the old card number to reuse
        self.casino_player.stats['Bingo']['_last squares'] = self.cards.get_card_numbers()
        #
        # Remove old cards
        for card in self.cards:
            self.all_cards.remove(card)
            self.ui.remove(card)
        for card in self.dealer_cards:
            self.all_cards.remove(card)
        #
        # Create new cards
        self.create_card_collection()
        self.cards.set_card_numbers(self.casino_player.stats['Bingo'].get('_last squares', []))
        #
        for item in self.cards:
            self.all_cards.add(item)
        for item in self.dealer_cards:
            self.all_cards.add(item)
        for item in self.cards:
            self.ui.append(item)
        self.restart_game(None, None)

    def highlight_patterns(self, pattern, one_shot):
        """Test method to cycle through the winning patterns"""
        self.log.debug('Creating new highlight pattern generators')
        for card in self.cards:
            self.add_generator(
                'highlight-patterns-card-%s' % card.name,
                self.highlight_pattern(card, pattern, one_shot)
            )

    def highlight_pattern(self, card, pattern, one_shot):
        """Highlight a particular pattern on a card"""
        for squares in pattern.get_matches(card):
            for square in squares:
                square.highlighted_state = bingocard.S_GOOD
            yield 100
            for square in squares:
                square.highlighted_state = bingocard.S_NONE
            yield 10
        #
        if not one_shot:
            self.add_generator('highlight', self.highlight_pattern(card, pattern, one_shot=False))

    def ball_picked(self, ball):
        """A ball was picked"""
        # Turn off the button to prevent the player from accidentally choosing another
        # ball at the same time
        self.add_generator('next-chip-animation', self.animate_next_chip())
        #
        # If auto-picking then update the cards
        auto_pick_cards = list(self.dealer_cards)
        if self.auto_pick:
            auto_pick_cards.extend(self.cards)
        for card in auto_pick_cards:
            card.call_square(ball.number)
        #
        # Highlight the card labels
        for card in self.all_cards:
            card.highlight_column(ball.letter)

    def player_picked(self, square, arg):
        """The player picked a square"""
        if not square.card.is_active:
            return
        #
        # Check to see if we created a new potentially winning square
        called_squares = list(square.card.called_squares)
        prior_called_squares = list(called_squares)
        prior_called_squares.remove(square.text)
        #
        _, winners = self.winning_pattern.get_number_to_go_and_winners(square.card, called_squares)
        _, prior_winners = self.winning_pattern.get_number_to_go_and_winners(square.card, prior_called_squares)
        self.log.debug('{0} / {1}'.format(winners, prior_winners))
        #
        if len(winners) > len(prior_winners):
            self.play_sound('bingo-potential-winner')
        #
        # Increment sound if we did this quickly
        if time.time() - self.last_pick_time < S['player-pick-interval']:
            self.current_pick_sound = min(self.current_pick_sound + 1, len(S['player-pick-sounds']) - 1)
        else:
            self.current_pick_sound = 0
        self.last_pick_time = time.time()
        self.play_sound(S['player-pick-sounds'][self.current_pick_sound])
        #
        self.log.info('Player picked {0}'.format(square))

    def player_unpicked(self, square, arg):
        """The player unpicked a square"""
        self.log.info('Player unpicked {0}'.format(square))
        self.play_sound('bingo-unpick')

    def flash_potential_winners(self):
        """Flash the squares that are potential winners"""
        while True:
            for state, delay in S['card-focus-flash-timing']:
                for card in self.all_cards:
                    for square in card.potential_winning_squares:
                        square.is_focused = state
                yield delay * 1000

    def play_sound(self, name):
        """Play a named sound - respects the mute settings"""
        if not self.sound_muted:
            prepare.SFX[name].play()

    def get_missing_squares(self, squares):
        """Return a list of the numbers that have not been called"""
        return [square for square in squares if square.text not in self.ball_machine.called_balls]

    def card_completed(self, card, arg):
        """A card was completed"""
        self.log.info('Card {0} owned by {1} was completed'.format(card.index, card.card_owner))
        #
        # Find the matching card from the dealer or player and deactivate it
        other_card = self.cards[card.index] if card.card_owner == bingocard.T_DEALER else self.dealer_cards[card.index]
        other_card.active = False
        other_card.set_card_state(bingocard.S_LOST)
        #
        # Check for all cards done
        for item in self.cards:
            if item.active and item != card:
                return
        else:
            for item in self.cards:
                self.add_generator('flash-labels', item.flash_labels())

    def randomly_highlight_buttons(self, source_button, buttons, number_of_times, delay, final_callback):
        """Randomly highlight buttons in a group and then call the callback when complete"""
        last_chosen = None
        source_button.state = True
        #
        # Turn all buttons off
        for button in buttons:
            button.state = False
        #
        for i in range(number_of_times):
            #
            # Choose one to highlight, but not the last one
            while True:
                chosen = random.choice(buttons)
                if chosen != last_chosen:
                    break
            #
            # Highlight it
            self.log.debug('Setting to button {0}, {1}'.format(buttons.index(chosen), chosen.name))
            chosen.state = True
            if last_chosen:
                last_chosen.state = False
            last_chosen = chosen
            #
            self.play_sound('bingo-beep')
            #
            if i != number_of_times - 1:
                yield delay
            #
            # Shortern delay
            delay *= S['randomize-button-speed-up']
        #
        source_button.state = False
        #
        final_callback(chosen)

