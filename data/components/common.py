"""Some common components to aid in the construction of game logic"""

"""Utility functions - some of these could go be refactored into the core eventually"""

import collections
import pygame as pg

from . import labels
from .. import prepare
from .. import tools
from ..events import EventAware

from . import loggable


# Events for the components
E_MOUSE_CLICK = 'mouse-click'
E_RIGHT_MOUSE_CLICK = 'right-mouse-click'
E_MOUSE_ENTER = 'mouse-enter'
E_MOUSE_MOVE = 'mouse-move'
E_MOUSE_LEAVE = 'mouse-leave'


def getLabel(name, position, text, settings):
    """Return a label using properties defined in the settings dictionary"""
    return labels.Label(
        path=settings["{}-font".format(name)],
        color=settings["{}-font-color".format(name)],
        size=settings["{}-font-size".format(name)],
        text=str(text),
        rect_attr={"center": position},
    )


class Clickable(EventAware, loggable.Loggable):
    """Simple class to make an item clickable

    To receive events generated by this object call the
    linkEvents method. For example,

    btn.linkEvent(E_MOUSE_CLICK, my_handler_function, arg=123)

    And my_handler_function(btn, 123) will be called whenever
    someone clicks on the object.

    """

    def __init__(self, name, rect=None):
        """Initialise the clickable"""
        self.initEvents()
        self.addLogger()
        #
        self.name = name
        self.rect = rect
        self.mouse_over = False

    def process_events(self, event, scale=(1, 1)):
        """Process pygame events"""
        pos = tools.scaled_mouse_pos(scale, event.pos)
        #
        if event.type == pg.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(pos):
                if event.button == 1:
                    self.handle_click()
                elif event.button == 3:
                    self.handle_right_click()
        elif event.type == pg.MOUSEMOTION:
            mouse_over = self.rect.collidepoint(pos)
            if mouse_over != self.mouse_over:
                if self.mouse_over:
                    self.handle_mouse_leave()
                else:
                    self.handle_mouse_enter()
            self.mouse_over = mouse_over

    def handle_click(self):
        """Do something when we are clicked on"""
        self.processEvent((E_MOUSE_CLICK, self))

    def handle_right_click(self):
        """Do something when we are clicked on with the right button"""
        self.processEvent((E_RIGHT_MOUSE_CLICK, self))

    def handle_mouse_enter(self):
        """Do something when the mouse enters our rect"""
        self.processEvent((E_MOUSE_ENTER, self))

    def handle_mouse_leave(self):
        """Do something when the mouse leaves our rect"""
        self.processEvent((E_MOUSE_LEAVE, self))


class ClickableGroup(list, EventAware):
    """A list of clickable items"""

    def __init__(self, items=None):
        """Initialise the group"""
        super(ClickableGroup, self).__init__(items if items else [])
        #
        self.initEvents()

    def process_events(self, event, scale=(1, 1)):
        """Process all the events"""
        for item in self:
            item.process_events(event, scale)

    def clear(self):
        """Remove all the items from the group

        Compatibility method for python2, where lists don't have a clear method

        """
        try:
            super(ClickableGroup, self).clear()
        except AttributeError:
            self[:] = []


class Drawable(object):
    """Simple base class for all screen objects"""

    def draw(self, surface):
        """Draw this item onto the given surface"""
        raise NotImplementedError('Need to implement the draw method')


class DrawableGroup(list, Drawable):
    """A list of drawable items"""

    def draw(self, surface):
        """Draw all these items onto the given surface"""
        for item in self:
            item.draw(surface)

    def clear(self):
        """Remove all the items from the group

        Compatibility method for python2, where lists don't have a clear method

        """
        try:
            super(DrawableGroup, self).clear()
        except AttributeError:
            self[:] = []


class KeyedDrawableGroup(collections.OrderedDict, Drawable):
    """A drawable group based on a dictionary so you can retrieve items"""

    def draw(self, surface):
        """Draw all the items to the given surface"""
        for item in self.values():
            item.draw(surface)


class NamedSprite(Drawable):
    """A sprite loaded from a named file"""

    def __init__(self, name, position, filename=None, scale=1.0):
        """Initialise the sprite"""
        super(NamedSprite, self).__init__()
        #
        self.name = name
        self.angle = 0
        self.sprite = prepare.GFX[filename if filename else name]
        w, h = self.sprite.get_size()
        #
        # Scale if needed
        if scale != 1.0:
            self.sprite = pg.transform.scale(self.sprite, (int(w * scale), int(h * scale)))
            w, h = w * scale, h * scale
        #
        self.rect = pg.Rect(position[0] - w / 2, position[1] - h / 2, w, h)

    def draw(self, surface):
        """Draw the sprite"""
        surface.blit(self.sprite, self.rect)

    def rotate_to(self, angle):
        """Rotate the sprite"""
        delta = angle - self.angle
        x, y = self.rect.x + self.rect.width / 2, self.rect.y + self.rect.height / 2
        self.sprite = pg.transform.rotate(self.sprite, delta)
        w, h = self.sprite.get_size()
        self.rect = pg.Rect(x - w / 2, y - h / 2, w, h)

    @classmethod
    def from_sprite_sheet(cls, name, sheet_size_in_sprites, sprite_cell, position, filename=None, scale=1.0):
        """Return a sprite from a particular position in a sprite-sheet"""
        #
        # Get a sprite
        new_sprite = cls(name, position, filename, scale)
        cols, rows = sheet_size_in_sprites
        w = new_sprite.rect.width / cols
        h = new_sprite.rect.height / rows
        #
        # Now split the sheet and reset the image
        sheet = tools.strip_from_sheet(new_sprite.sprite, (0, 0), (w, h), cols, rows)
        new_sprite.sprite = sheet[sprite_cell[0] + sprite_cell[1] * cols]
        new_sprite.rect = pg.Rect(position[0] - w / 2, position[1] - h / 2, w, h)
        #
        return new_sprite


class ImageButton(Clickable):
    """A button with an image and text

    To receive events call the linkEvent method as described in the Clickable
    documentation.

    """

    def __init__(self, name, position, filename, text_properties, text,
                 settings, scale=1.0):
        """Initialise the button"""
        #
        self.image = NamedSprite(name, position, filename, scale=scale)
        self.label = getLabel(text_properties, position, text, settings)
        #
        super(ImageButton, self).__init__(name, self.image.rect)

    def draw(self, surface):
        """Draw the button"""
        self.image.draw(surface)
        self.label.draw(surface)


class ImageOnOffButton(Clickable):
    """A button with an on and off image and text

    To receive events call the linkEvent method as described in the Clickable
    documentation.

    """

    def __init__(self, name, position, on_filename, off_filename, text_properties, text, state,
                 settings, scale=1.0):
        """Initialise the button"""
        self.state = state
        #
        self.on_image = NamedSprite(name, position, on_filename, scale=scale)
        self.off_image = NamedSprite(name, position, off_filename, scale=scale)
        self.label = getLabel(text_properties, position, text, settings)
        #
        super(ImageOnOffButton, self).__init__(name, self.on_image.rect)

    def draw(self, surface):
        """Draw the button"""
        if self.state:
            self.on_image.draw(surface)
        else:
            self.off_image.draw(surface)
        self.label.draw(surface)


class MultiStateButton(Clickable):
    """A button with multiple states

    To receive events call the linkEvent method as described in the Clickable
    documentation.

    """

    def __init__(self, name, position, filenames, text_properties, text, state,
                 settings, scale=1.0):
        """Initialise the button"""
        self.state = state
        #
        self.images = [NamedSprite(name, position, filename, scale=scale) for filename in filenames]
        self.label = getLabel(text_properties, position, text, settings)
        #
        super(MultiStateButton, self).__init__(name, self.images[0].rect)

    def draw(self, surface):
        """Draw the button"""
        self.images[self.state].draw(surface)
        self.label.draw(surface)
