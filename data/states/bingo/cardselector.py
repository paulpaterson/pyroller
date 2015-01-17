"""Component that allows the player to select how many cards to play"""

import pygame as pg
from ...events import EventAware
from ...components import common
from . import loggable
from .settings import SETTINGS as S
from . import events


class CardSelector(common.DrawableGroup, loggable.Loggable, EventAware):
    """Component to allow the player to select how many cards to play"""
    
    def __init__(self, name, state):
        """Initialise the component"""
        common.DrawableGroup.__init__(self)
        self.addLogger()
        self.initEvents()
        #
        self.name = name
        self.state = state
        #
        self.ui = self.create_ui()
        self.number_of_cards = S['card-selection-default']

    def create_ui(self):
        """Create the UI for the component"""
        ui = common.ClickableGroup()
        #
        x, y = S['card-selection-position']
        #
        # Create buttons
        for idx, (text, number, (dx, dy)) in enumerate(S['card-selection']):
            button = common.ImageOnOffButton(
                text, (x + dx, y + dy),
                'bingo-blue-button', 'bingo-blue-off-button', 'card-selection',
                text,
                number == S['card-selection-default'],
                S, scale=S['card-selection-scale']
            )
            button.linkEvent(common.E_MOUSE_CLICK, self.select_card_number, (idx, number))
            self.add_original(button)
            ui.append(button)
        #
        return ui

    def select_card_number(self, obj, arg):
        """A card selection button was pressed"""
        clicked_idx, number = arg
        #
        if number is None:
            self.state.add_generator('random-button-flash', self.state.randomly_highlight_buttons(
                self.original_objects[-1], self.original_objects[:-1],
                S['randomize-button-number'], S['randomize-button-delay'],
                lambda b: self.select_card_number(
                    None, (self.original_objects.index(b), self.original_objects.index(b) + 1))
            ))
            return
        #
        self.number_of_cards = number
        self.log.info('Pressed card selection button {0}, number cards {1}'.format(clicked_idx, number))
        for idx, button in enumerate(self.ui):
            button.state = idx == clicked_idx
        #
        self.processEvent((events.E_NUM_CARDS_CHANGED, number))