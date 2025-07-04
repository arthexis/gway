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


def find_awg(
    *,
    meters: Union[int, str, None] = None,  # Required
    amps: Union[int, str] = "40",
    volts: Union[int, str] = "220",
    material: Literal["cu", "al", "?"] = "cu",
    max_awg: Optional[Union[int, str]] = None,
    max_lines: Union[int, str] = "1",
    phases: Literal["1", "3", 1, 3] = "2",
    temperature: Union[int, str, None] = None,
    conduit: Optional[Union[str, bool]] = None,
    ground: Union[int, str] = "1"
):
    """
    Calculate the type of cable needed for an electrical system.

    Args:
        meters: Cable length (one line) in meters. Required keyword.
        amps: Load in Amperes. Default: 40 A.
        volts: System voltage. Default: 220 V.
        material: 'cu' (copper) or 'al' (aluminum). Default: cu.
        max_awg: Optional maximum gauge number allowed. If provided,
            cables thicker than this won't be considered. Example: ``6`` or ``1/0``.
        max_lines: Maximum number of line conductors allowed. Default: 1
        phases: Number of phases for AC (1, 2 or 3). Default: 2
        temperature: Conductor temperature rating in Celsius. Use ``60``, ``75``
            or ``90``. ``None`` (default) selects 60C for loads <=100A and 75C
            otherwise.
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
    if max_awg is not None:
        max_awg = AWG(max_awg)
    phases = int(phases)
    temperature = None if temperature in (None, "", "auto") else int(temperature)
    ground = int(ground)

    assert amps >= 10, f"Minimum load for this calculator is 15 Amps.  Yours: {amps=}."
    assert (amps <= 546) if material == "cu" else (amps <= 430), f"Max. load allowed is 546 A (cu) or 430 A (al). Yours: {amps=} {material=}"
    assert meters >= 1, "Consider at least 1 meter of cable."
    assert 110 <= volts <= 460, f"Volt range supported must be between 110-460. Yours: {volts=}"
    assert material in ("cu", "al"), "Material must be 'cu' (copper) or 'al' (aluminum)."
    assert phases in (1, 2, 3), "AC phases 1, 2 or 3 to calculate for. DC not supported."
    if temperature is not None:
        assert temperature in (60, 75, 90), "Temperature must be 60, 75 or 90"

    with gw.sql.open_connection(autoload=True) as cursor:

        # Use correct voltage drop formula: includes current (amps)
        if phases in (2, 3):
            expr = "sqrt(3) * :meters * :amps * k_ohm_km / 1000"
        else:
            expr = "2 * :meters * :amps * k_ohm_km / 1000"

        if temperature is None:
            amp_clause = "(amps_75c >= :amps AND :amps > 100) OR (amps_60c >= :amps AND :amps <= 100)"
        else:
            amp_clause = f"amps_{temperature}c >= :amps"

        sql = f"""
            SELECT awg_size, line_num, {expr} AS vdrop
            FROM awg_cable_size
            WHERE (material = :material OR :material = '?')
              AND {amp_clause}
              AND line_num <= :max_lines
              {"" if max_awg is None else "AND awg_size <= :max_awg"}
            ORDER BY awg_size DESC
        """
        params = {
            "amps": amps,
            "meters": meters,
            "material": material,
            "volts": volts,
            "max_lines": max_lines,
        }
        if max_awg is not None:
            params["max_awg"] = int(max_awg)
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
                    "temperature": temperature if temperature is not None else (60 if amps <= 100 else 75),
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

        # If no suitable cable found
        gw.debug("No cable found within voltage drop limit (3%).")
        if max_awg is not None and candidates:
            # Return best effort with warning
            awg_size, line_num, vdrop = candidates[0]
            awg_res = AWG(awg_size)
            perc = vdrop / volts
            cables = line_num * (phases + ground)
            result = {
                "awg": str(awg_res),
                "meters": meters,
                "amps": amps,
                "volts": volts,
                "temperature": temperature if temperature is not None else (60 if amps <= 100 else 75),
                "lines": line_num,
                "vdrop": vdrop,
                "vend": volts - vdrop,
                "vdperc": perc * 100,
                "cables": f"{cables - 1}+{ground}",
                "total_meters": f"{(cables - 1) * meters}+{meters*ground}",
                "warning": "Voltage drop exceeds 3% with given max_awg",
            }
            if conduit:
                if conduit is True:
                    conduit = "emt"
                fill = find_conduit(awg_res, cables, conduit=conduit)
                result["conduit"] = conduit
                result["pipe_inch"] = fill["size_inch"]
            gw.debug(f"Returning best effort with warning: {result}")
            return result

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
    max_lines="3", max_awg=None, phases="1", temperature=None,
    conduit=None, neutral="0", **kwargs
):
    """Page builder for AWG cable finder with HTML form and result."""
    # TODO: Add a image with the sponsor logo on the right side of the result page
    if not meters:
        return '''<link rel="stylesheet" href="/static/awg/cable_finder.css">
            <h1>AWG Cable Finder</h1>
            <form method="post" class="cable-form">
                <label>Meters:<input type="number" name="meters" required min="1" /></label>
                <label>Amps:<input type="number" name="amps" value="40" /></label>
                <label>Volts:<input type="number" name="volts" value="220" /></label>
                <label>Material:
                    <select name="material">
                        <option value="cu">Copper (cu)</option>
                        <option value="al">Aluminum (al)</option>
                    </select>
                </label>
                <label>Phases:
                    <select name="phases">
                        <option value="2">AC Two Phases (2)</option>
                        <option value="1">AC Single Phase (1)</option>
                        <option value="3">AC Three Phases (3)</option>
                    </select>
                </label>
                <label>Temperature:
                    <select name="temperature">
                        <option value="auto">Auto</option>
                        <option value="60">60C</option>
                        <option value="75">75C</option>
                        <option value="90">90C</option>
                    </select>
                </label>
                <label>Max AWG:<input type="text" name="max_awg" /></label>
                <label>Max Lines:<input type="number" name="max_lines" value="1" /></label>
                <button type="submit" class="submit">Find Cable</button>
            </form>
        '''
    try:
        result = find_awg(
            meters=meters, amps=amps, volts=volts,
            material=material, max_lines=max_lines, phases=phases,
            max_awg=max_awg, temperature=temperature,
        )
    except Exception as e:
        return f"<p class='error'>Error: {e}</p><p><a href='/awg/cable-finder'>&#8592; Try again</a></p>"

    if result.get("awg") == "n/a":
        return """
            <h1>No Suitable Cable Found</h1>
            <p>No cable was found that meets the requirements within a 3% voltage drop.<br>
            Try adjusting the <b>cable size, amps, length, or material</b> and try again.</p>
            <p><a href="/awg/cable-finder">&#8592; Calculate again</a></p>
        """

    return f"""
        <h1>Recommended Cable</h1>
        <ul>
            <li><strong>AWG Size:</strong> {result['awg']}</li>
            <li><strong>Lines:</strong> {result['lines']}</li>
            <li><strong>Total Cables:</strong> {result['cables']}</li>
            <li><strong>Total Length (m):</strong> {result['total_meters']}</li>
            <li><strong>Voltage Drop:</strong> {result['vdrop']:.2f} V ({result['vdperc']:.2f}%)</li>
            <li><strong>Voltage at End:</strong> {result['vend']:.2f} V</li>
            <li><strong>Temperature Rating:</strong> {result['temperature']}C</li>
        </ul>
        {f"<p class='warning'>{result['warning']}</p>" if result.get('warning') else ''}
        <p>
        <em>Special thanks to the expert electrical engineers at <strong>
        <a href="https://www.gelectriic.com">Gelectriic Solutions</a></strong> for their 
        useful input and support while creating this calculator.</em>
        </p>
        <p><a href="/awg/cable-finder">&#8592; Calculate again</a></p>
    """
