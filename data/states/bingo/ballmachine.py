"""Represents the machine that picks numbers"""

import random
import pygame as pg

from ...components import common
from . import loggable
from .settings import SETTINGS as S
from . import statemachine


class Ball(object):
    """A ball representing a number in the game"""

    def __init__(self, number):
        """Initialise the ball"""
        self.number = number
        #
        # Get the name for this ball (eg B1, I20)
        number_lookup = S['card-numbers']
        for letter, col in zip('BINGO', sorted(number_lookup.keys())):
            numbers = number_lookup[col]
            if number in numbers:
                self.letter = letter
                self.col = col
                break
        else:
            raise ValueError('Could not locate details for {0}'.format(number))
        #
        self.full_name = '{0}{1}'.format(self.letter, self.number)


class BallMachine(common.Drawable, loggable.Loggable):
    """A machine to pick balls at random"""

    def __init__(self, name, state):
        """Initialise the machine"""
        self.addLogger()
        self.name = name
        self.state = state
        #
        self.all_balls = [Ball(n) for n in S['machine-balls']]
        self.balls = []
        self.called_balls = []
        self.speed_buttons = common.pg.sprite.LayeredDirty()
        self.buttons = common.ClickableGroup()
        self.current_ball = None
        self.interval = self.initial_interval = S['machine-speeds'][0][1] * 1000
        self.running = False
        self.timer = None
        self.speed_transitions = {}
        #
        self.ui = self.create_ui()
        self.reset_machine()

    def create_ui(self):
        """Create the UI components"""
        components = common.pg.sprite.LayeredDirty()
        #
        # The display of all the balls that have been called
        self.called_balls_ui = CalledBallTray(S['called-balls-position'], self.state)
        components.add(self.called_balls_ui)
        #
        # Speed increases based on the number of balls called
        for idx, (name, interval, number_balls) in enumerate(S['machine-speeds']):
            self.speed_transitions[number_balls] = (idx, interval)
        #
        self.cog = CogWheel(self)
        components.add(self.cog)
        #
        # The spout showing progress towards a new ball
        self.spout_sprites = [
            common.NamedSprite('bingo-spout-{0}'.format(i), S['spout-position']) for i in range(S['spout-number'])
        ]
        #
        return components

    def change_speed(self, obj,  arg, silent=False):
        """Change the speed of the ball machine"""
        selected_idx, interval = arg
        self.log.info('Changing machine speed to index {0}, {1}s'.format(selected_idx, interval))
        #
        # Play appropriate sound
        if not silent:
            if interval < self.interval / 1000:
                self.state.play_sound('bingo-speed-up')
            else:
                self.state.play_sound('bingo-slow-down')
        #
        # Set cog
        self.cog.set_speed(selected_idx)
        #
        # Set speed of the machine
        self.reset_timer(interval * 1000)

    def start_machine(self):
        """Start the machine"""
        self.running = True
        if self.timer:
            try:
                self.state.stop_generator('ball-machine')
            except statemachine.NotFound:
                # OK, must have already completed
                pass

        self.timer = self.state.add_generator('ball-machine', self.pick_balls())

    def stop_machine(self):
        """Stop the machine"""
        self.running = False

    def reset_timer(self, interval):
        """Reset the timer on the machine"""
        self.interval = interval
        if self.timer:
            self.timer.update_interval(interval)

    def reset_machine(self, interval=None):
        """Reset the machine"""
        self.balls = list(self.all_balls)
        self.called_balls = []
        random.shuffle(self.balls)
        self.called_balls_ui.reset_display()
        self.change_speed(None, (0, S['machine-speeds'][0][1]), silent=True)
        self.start_machine()

    def pick_balls(self):
        """Pick the balls"""
        for idx, ball in enumerate(self.balls):
            #
            # Under some circumstances we will restart this iterator so this
            # makes sure we don't repeat balls
            if ball.number in self.called_balls:
                continue
            #
            self.called_balls.append(ball.number)
            self.set_current_ball(ball)
            self.state.play_sound('bingo-ball-chosen')
            #
            # Watch for speed transition
            try:
                button_idx, new_interval = self.speed_transitions[idx]
            except KeyError:
                # No transition
                pass
            else:
                self.change_speed(None, (button_idx, new_interval))
            #
            # Wait for next ball
            yield self.interval

    def set_current_ball(self, ball):
        """Set the current ball"""
        self.log.info('Current ball is {0}'.format(ball.full_name))
        #
        self.current_ball = ball
        self.state.ball_picked(ball)
        self.called_balls_ui.call_ball(ball)

    def draw(self, surface):
        """Draw the machine"""
        #
        self.ui.draw(surface)
        self.called_balls_ui.dropping_balls.draw(surface)
        self.called_balls_ui.moving_balls.draw(surface)
        #
        self.called_balls_ui.update(self.state.dt * S['conveyor-speed'] / self.interval)
        self.cog.update(self.state.dt * S['machine-cog-speed'] / self.interval)
        #
        # Calculate how close we are to choosing a new ball
        fraction = 1.0 - self.timer.get_fraction_to_go()
        if fraction > 0.95:
            spout_sprite = self.spout_sprites[-1]
        else:
            spout_sprite = self.spout_sprites[int(fraction * (S['spout-number'] - 1))]
        spout_sprite.dirty = True
        spout_sprite.draw(surface)

    def call_next_ball(self):
        """Immediately call the next ball"""
        self.timer.next_step()


class CalledBallTray(pg.sprite.LayeredDirty, loggable.Loggable):
    """A display of the balls that have been called"""

    def __init__(self, position, state):
        """Initialise the display"""
        pg.sprite.LayeredDirty.__init__(self)
        self.addLogger()
        self.state = state
        #
        self.x, self.y = position
        self.called_balls = []
        #
        self.conveyor = common.NamedSprite(
            'bingo-conveyor',
            S['conveyor-position'],
            )
        self.initial_x = S['conveyor-position'][0]
        self.current_x = 0
        #
        self.dropping_balls = common.pg.sprite.LayeredDirty()
        self.moving_balls = common.pg.sprite.LayeredDirty()
        #
        self.add(common.NamedSprite('bingo-grill', S['machine-background-position']))
        self.add(self.dropping_balls)
        self.add(self.moving_balls)
        self.add(self.conveyor)

    def call_ball(self, ball):
        """Call a particular ball"""
        self.called_balls.append(ball)
        ball_ui = SingleBallDisplay('ball', S['machine-ball-position'], ball, self)
        self.dropping_balls.add(ball_ui)
        self.state.add_generator('ball-falling', self.ball_falling(ball_ui))

    def reset_display(self):
        """Reset the display of the balls"""
        self.called_balls = []
        self.dropping_balls.empty()
        self.moving_balls.empty()

    def update(self, increment):
        """Update the display of the tray"""
        self.current_x += increment
        if self.current_x > S['conveyor-repeat']:
            self.current_x -= S['conveyor-repeat']
        self.conveyor.rect.x = self.initial_x + self.current_x
        self.conveyor.dirty = True
        self.move_balls(increment)

    def ball_falling(self, ball):
        """Cause a ball to fall down to the conveyor"""
        drop_speed = S['machine-ball-drop-initial-speed']
        while ball.y < S['conveyor-ball-position']:
            ball.y += drop_speed
            drop_speed += S['machine-ball-drop-acceleration']
            yield 10
        self.moving_balls.add(ball)
        #
        # Remove from the list - note that we have to check the ball is still there
        # because the machine may have been reset between the 'yield' and here
        if ball in self.dropping_balls:
            self.dropping_balls.remove(ball)

    def move_balls(self, increment):
        """Move the balls"""
        for ball in reversed(self.moving_balls.sprites()):
            ball.x += increment
            if ball.x >= S['conveyor-ball-drop-off']:
                self.moving_balls.remove(ball)


class SingleBallDisplay(common.Drawable, loggable.Loggable):
    """A ball displayed on the screen"""

    def __init__(self, name, position, ball, state):
        """Initialise the ball"""
        common.Drawable.__init__(self)
        self.addLogger()
        #
        self.name = name
        self.state = state
        #
        # Create the background chip
        self.bg = common.NamedSprite.from_sprite_sheet(
            'chips', (2, 5),
            S['called-ball-sprite-lookup'][ball.col], position,
            scale=S['machine-ball-sprite-scale']
        )
        #
        # And the text for the number
        self.text = common.getLabel(
            'machine-ball',
            (self.bg.rect.width / 2, self.bg.rect.height / 2), str(ball.number), S
        )
        self.text.color = pg.Color(S['called-ball-font-color'][ball.col])
        self.text.update_text()
        #
        # Write the number on the background
        self.text.draw(self.bg.image)
        #
        # And rotate a bit
        self.bg.rotate_to(random.uniform(*S['machine-ball-angle-range']))
        w, h = self.bg.image.get_size()
        self.rect = pg.Rect(position[0] - w / 2, position[1] - h / 2, w, h)
        self.image = self.bg.image

    @property
    def y(self):
        return self.rect.y

    @y.setter
    def y(self, value):
        self.rect.y = value
        self.dirty = True

    @property
    def x(self):
        return self.rect.x

    @x.setter
    def x(self, value):
        self.rect.x = value
        self.dirty = True


class CogWheel(common.Drawable):
    """Visual display of the cog"""

    def __init__(self, state):
        """Initialise the cog"""
        common.Drawable.__init__(self)
        self.state = state
        #
        self.sprites = [
            common.NamedSprite(
                'bingo-cog-{0}'.format(i),
                S['machine-cog-position'],
            ) for i in range(len(S['machine-speeds']))
        ]
        self.speed = 0
        self.angle = 0
        self.set_speed(0)
        self.image = self.sprites[0].image
        self.rect = pg.Rect(S['machine-cog-position'][0], S['machine-cog-position'][1],
                            *self.image.get_size())

    def set_speed(self, speed):
        """Set the current speed"""
        self.speed = speed

    def update(self, increment):
        """Update the display of the cog"""
        self.angle = (self.angle + increment) % 360
        # TODO: refactor the rotation logic - should be built into sprite
        surface = self.sprites[self.speed].image.copy()
        x, y = self.rect.x + self.rect.width / 2, self.rect.y + self.rect.height / 2
        self.image = pg.transform.rotozoom(surface, self.angle, 1.0)
        w, h = self.image.get_size()
        self.rect = pg.Rect(x - w / 2, y - h / 2, w, h)
        #
        self.dirty = True