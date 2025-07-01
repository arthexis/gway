# file: projects/mtg.py

import requests

def search(query, *, show=True, limit=5, **kwargs):
    """
    Search for Magic: The Gathering cards using Scryfall API.

    Parameters:
        query (str): The search query (name, text, type, etc.)
        show (bool): If True, print the card(s) info; else, return the results.
        **kwargs: Extra parameters for the Scryfall search API.

    Returns:
        list of dict: List of matching card data dicts if show=False.
        None: If show=True (prints results directly).
    """
    # Construct the query parameters
    params = {'q': query}
    params.update(kwargs)
    url = "https://api.scryfall.com/cards/search"
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error searching Scryfall: {e}")
        return None

    if data.get('object') != 'list' or not data.get('data'):
        print("No cards found for that query.")
        return None

    cards = data['data']

    if show:
        for card in cards[:limit]:  # Show up to 5 results
            print(f"\n--- {card.get('name', 'Unknown')} ---")
            print(f"Set: {card.get('set_name', 'Unknown')} ({card.get('set').upper()})")
            print(f"Type: {card.get('type_line', '-')}")
            if card.get('mana_cost'):
                print(f"Mana Cost: {card['mana_cost']}")
            if card.get('oracle_text'):
                print(f"Text: {card['oracle_text']}")
            if card.get('power') or card.get('toughness'):
                print(f"P/T: {card.get('power', '')}/{card.get('toughness', '')}")
            if card.get('image_uris', {}).get('normal'):
                print(f"Image: {card['image_uris']['normal']}")
    else:
        return cards
