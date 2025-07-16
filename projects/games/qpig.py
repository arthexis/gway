"""Quantum Piggy Farm view skeleton served by GWAY."""
from gway import gw

def view_qpig_farm(*_, **__):
    """Return the basic HTML frame for the Quantum Piggy Farm game."""
    gw.debug("view_qpig_farm called")
    html = [
        '<link rel="stylesheet" href="/static/games/qpig/qpig_farm.css">',
        '<h1>Quantum Piggy Farm</h1>',
        '<div class="qpig-garden tab-garden">',
        '<div class="qpig-tabs">',
        '<button class="qpig-tab active" data-tab="garden">Garden Shed</button>',
        '<button class="qpig-tab" data-tab="market">Market Street</button>',
        '<button class="qpig-tab" data-tab="lab">Quantum Lab</button>',
        '<button class="qpig-tab" data-tab="travel">Travel Abroad</button>',
        '<button class="qpig-tab" data-tab="settings">Game Settings</button>',
        '</div>',
        '<div id="qpig-panel-garden" class="qpig-panel active">',
        '<div class="qpig-top"><span id="qpig-count"></span>'
        '<span id="qpig-pellets"></span></div>',
        '<div class="qpig-pigs">',
        '<div id="pig-template" class="qpig-pig-card" style="display:none;">',
        '<div class="qpig-pig-info">',
        '<div><span class="qpig-pig-name">Name</span> — '
        '<em class="qpig-pig-activity">Resting</em></div>',
        '<div class="qpig-pig-stats"></div>',
        '</div>',
        '<img class="qpig-photo" src="" width="30" height="30">',
        '</div>',
        '</div>',
        '</div>',
        '<div id="qpig-panel-market" class="qpig-panel">',
        '<div class="qpig-top"><span id="qpig-vcreds"></span></div>',
        '<div id="market-stalls"></div></div>',
        '<div id="qpig-panel-lab" class="qpig-panel">',
        '<div class="qpig-top">',
        '<span id="qpig-lab-pellets"></span>'
        '<span id="qpig-lab-vcreds"></span>',
        '</div>',
        '<table id="qpig-lab-ops" class="lab-ops">',
        '<tr><th>Operation</th><th>Time</th><th></th></tr>',
        '<tr><td>Measure Spin</td><td>5s</td>'
        '<td><button data-op="measure" data-time="5">Start</button></td></tr>',
        '<tr><td>Entangle Pair</td><td>10s</td>'
        '<td><button data-op="entangle" data-time="10">Start</button></td></tr>',
        '<tr><td>Collect Quantum Pellets</td><td>3s</td>'
        '<td><button data-op="collect" data-time="3">Start</button></td></tr>',
        '</table>',
        '<progress id="lab-progress" value="0" max="100" '
        'style="display:none;width:100%"></progress>',
        '</div>',
        '<div id="qpig-panel-travel" class="qpig-panel">'
        '<div class="qpig-top"></div>Travel Abroad coming soon</div>',
        '<div id="qpig-panel-settings" class="qpig-panel">'
        '<div class="qpig-top"></div>',
        '<div class="qpig-buttons">',
        "<button type='button' id='qpig-save' title='Save'>💾 Save</button>",
        "<button type='button' id='qpig-load' title='Load'>📂 Load</button>",
        '</div></div>',
        '</div>',
        '</div>',
    ]
    return "\n".join(html)
