# file: projects/awg.py

from typing import Literal, Union, Optional
from gway import gw


class AWG(int):
    def __new__(cls, value):
        if isinstance(value, str) and "/" in value:
            value = -int(value.split("/")[0])
        return super().__new__(cls, int(value))

    def __str__(self):
        return f"{abs(self)}/0" if self < 0 else str(int(self))

    def __repr__(self):
        return f"AWG({str(self)})"


def find_cable(
    *,
    meters: Union[int, str, None] = None,  # Required
    amps: Union[int, str] = "40",
    volts: Union[int, str] = "220",
    material: Literal["cu", "al", "?"] = "cu",
    max_lines: Union[int, str] = "1",
    phases: Literal["1", "3", 1, 3] = "2",
    conduit: Optional[Union[str, bool]] = None,
    ground: Union[int, str] = "1"
):
    """
    Calculate the type of cable needed for an electrical system.

    Args:
        meters: Cable length (one line) in meters. Required keyword.
        amps: Load in Amperes. Default: 40 A.
        volts: System voltage. Default: 220 V.
        material: 'cu' (copper), 'al' (aluminum), or '?' (any). Default: cu.
        max_lines: Maximum number of line conductors allowed. Default: 1
        phases: Number of phases for AC (1, 2 or 3). Default: 2
        conduit: Conduit type or None.
        ground: Number of ground wires.
    Returns:
        dict with cable selection and voltage drop info, or {'awg': 'n/a'} if not possible.
    """
    gw.info(f"Calculating AWG for {meters=} {amps=} {volts=} {material=}")

     # Convert and validate inputs
    amps = int(amps)
    meters = int(meters)
    volts = int(volts)
    max_lines = int(max_lines)
    phases = int(phases)
    ground = int(ground)

    assert amps >= 20, "Min. charger load is 20 Amps."
    assert meters >= 1, "Consider at least 1 meter of cable."
    assert 110 <= volts <= 460, "Volt range is 110-460."
    assert material in ("cu", "al", "?"), "Material must be cu, al or ?."
    assert phases in (1, 2, 3), "Allowed phases 1, 2 or 3."

    with gw.sql.open_connection(autoload=True) as cursor:

        # Use correct voltage drop formula: includes current (amps)
        if phases in (2, 3):
            expr = "sqrt(3) * :meters * :amps * k_ohm_km / 1000"
        else:
            expr = "2 * :meters * :amps * k_ohm_km / 1000"

        sql = f"""
            SELECT awg_size, line_num, {expr} AS vdrop
            FROM awg_cable_size
            WHERE (material = :material OR :material = '?')
              AND ((amps_75c >= :amps AND :amps > 100)
                   OR (amps_60c >= :amps AND :amps <= 100))
              AND line_num <= :max_lines
            ORDER BY awg_size DESC
        """
        params = {
            "amps": amps,
            "meters": meters,
            "material": material,
            "volts": volts,
            "max_lines": max_lines,
        }
        gw.debug(f"AWG find-cable SQL candidates: {sql.strip()}, params: {params}")
        cursor.execute(sql, params)
        candidates = cursor.fetchall()
        gw.debug(f"AWG find-cable candidates fetched: {candidates}")

        # Iterate and pick first cable within voltage drop threshold (3%)
        for awg_size, line_num, vdrop in candidates:
            perc = vdrop / volts
            gw.debug(f"Evaluating AWG={awg_size}, lines={line_num}, vdrop={vdrop:.6f}, vdperc={perc*100:.4f}%")
            if perc <= 0.03:
                awg_res = AWG(awg_size)
                cables = line_num * (phases + ground)
                result = {
                    "awg": str(awg_res),
                    "meters": meters,
                    "amps": amps,
                    "volts": volts,
                    "lines": line_num,
                    "vdrop": vdrop,
                    "vend": volts - vdrop,
                    "vdperc": perc * 100,
                    "cables": f"{cables - 1}+{ground}",
                    "total_meters": f"{(cables - 1) * meters}+{meters*ground}",
                }
                if conduit:
                    if conduit is True:
                        conduit = "emt"
                    fill = find_conduit(awg_res, cables, conduit=conduit)
                    result["conduit"] = conduit
                    result["pipe_inch"] = fill["size_inch"]
                gw.debug(f"Selected cable result: {result}")
                return result

        # If no suitable cable found, return 'n/a'
        gw.debug("No cable found within voltage drop limit (3%). Returning 'n/a'.")
        return {"awg": "n/a"}


def find_conduit(awg, cables, *, conduit="emt"):
    """Calculate the kind of conduit required for a set of cables."""
    with gw.sql.open_connection() as cursor:

        assert conduit in ("emt", "imc", "rmc", "fmc"), "Allowed: emt, imc, rmc, fmc."
        assert 1 <= cables <= 30, "Valid for 1-30 cables per conduit."
        
        awg = AWG(awg)
        sql = f"""
            SELECT trade_size
            FROM awg_conduit_fill
            WHERE lower(conduit) = lower(:conduit)
            AND awg_{str(awg)} >= :cables
            ORDER BY trade_size DESC LIMIT 1  
        """

        cursor.execute(sql, {"conduit": conduit, "cables": cables})
        row = cursor.fetchone()
        if not row:
            return {"trade_size": "n/a"}

        return {"size_inch": row[0]}


def view_cable_finder(
    *, meters=None, amps="40", volts="220", material="cu", 
    max_lines="3", phases="1", conduit=None, neutral="0", **kwargs
):
    """Page builder for AWG cable finder with HTML form and result."""

    # TODO: Complete the interface to also calculate the counduit diameter estimation in one view

    if not meters:
        return '''<h1>AWG Cable Finder</h1>
            <form method="post">
                <label>Meters: <input type="number" name="meters" required min="1" /></label><br/>
                <label>Amps: <input type="number" name="amps" value="40" /></label><br/>
                <label>Volts: <input type="number" name="volts" value="220" /></label><br/>
                <label>Material: 
                    <select name="material">
                        <option value="cu">Copper (cu)</option>
                        <option value="al">Aluminum (al)</option>
                    </select>
                </label><br/>
                <label>Phases: 
                    <select name="phases">
                        <option value="2">AC Two Phases (2)</option>
                        <option value="1">AC Single Phase (1)</option>
                        <option value="3">AC Three Phases (3)</option>
                    </select>
                </label><br/>
                <label>Max Lines: <input type="number" name="max_lines" value="1" /></label><br/>
                <button type="submit" class="submit">Find Cable</button>
            </form>
        '''
    try:
        result = find_cable(
            meters=meters, amps=amps, volts=volts,
            material=material, max_lines=max_lines, phases=phases, 
        )
    except Exception as e:
        return f"<p class='error'>Error: {e}</p><p><a href='/awg/cable-finder'>&#8592; Try again</a></p>"

    return f"""
        <h1>Recommended Cable</h1>
        <ul>
            <li><strong>AWG Size:</strong> {result['awg']}</li>
            <li><strong>Lines:</strong> {result['lines']}</li>
            <li><strong>Total Cables:</strong> {result['cables']}</li>
            <li><strong>Total Length (m):</strong> {result['total_meters']}</li>
            <li><strong>Voltage Drop:</strong> {result['vdrop']:.2f} V ({result['vdperc']:.2f}%)</li>
            <li><strong>Voltage at End:</strong> {result['vend']:.2f} V</li>
        </ul>
        <p><a href="/awg/cable-finder">&#8592; Calculate again</a></p>
    """

