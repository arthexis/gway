# projects/deck.py

# TODO: Implement a simple card game helper for El Tomo del Poder

def shuffle(name, *, marks="seen held", **kwargs):
    # Creates a new deck in gw.resource('work','decks', 'name.txt')
    # (If name didn't include the txt extentions)
    # Names should be stored with underscores but may accept spaces or -
    # A blank deck file contains 54 lines each with:
    # <suit><number> <marks>
    # suit is one of: D = Spade, H=Clubs, C=Hearts, V=Diamonds
    # List the suits in the above order and with descending number
    # using A for 1, and Q, J, K after 10.
    # And the last two lines should be XX and XY to represent two Jokers
    # Marks are initially blank. The file is actually stored in order.
    # If requested to shuffle a deck that already exists, instead
    # just remove all instances of the given marks. Each mark is one word.
    # Lines after the first 54 are added to store metadata about the deck
    # The format of each of those lines is:
    # <key>=<data>
    # By default insert kwargs as extra metadata if provided
    # An additional datum must be added:
    # DEALT=0
    # All metadata should be preserved between shuffles except
    # DEALT which should be reset to zero whenever a deck is shuffled
    pass


# TODO: We should create a function to interpret and validate cards that we can reuse for 
# shuffle, draw, deal and other functions

# TODO: Keep track of the last deck we viewed in work/decks/latest.txt
# (Just store the name of the latest used deck there, and when we use
# latest as the deck name, we are meaning to look it up and use that)
# Maybe we should have a helper function for that case

def mark(*cards, name="latest", marks="marked"):
    # Adds a mark to the given card linen in the given deck if not already marked 
    pass

def draw(*cards, name="latest", marks=None):
    # Marks a card as 'held' and 'seen' plus any extra marks if provided
    # Then calculates the chance of next pulling each SUIT based on which cards are NOT 'held'
    # Then the DEALT metadata of the deck should be increased by the number of
    # cards removed (with the marks held/seen added)
    pass


def deal(number, name="latest"):
    # Increases the DEALT metadata by the given number but doesn't
    # mark any cards as drawn. This represents the dealer giving the player
    # a face-down card, which we don't want to rule out in calculations
    # but we need to be conscious we are 1 card down from the pile.
    pass

def count(name="latest"):
    # Show how many cards are left in the deck (not DEALT)
    # Plus show the same suit % calculation as when drawing (we could make it a separate func.)
    pass
