# file: projects/awg.py

from typing import Literal, Union, Optional
import math
from gway import gw


class AWG(int):
    """Represents an AWG gauge as an integer.
    Positive numbers are thin wires (e.g., 14),
    while zero and negative numbers use zero notation ("1/0", "2/0", ...).
    """
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
        ground: Number of ground wires per line.
    Returns:
        dict with cable selection and voltage drop info, or {'awg': 'n/a'} if not possible.
    """
    gw.info(f"Calculating AWG for {meters=} {amps=} {volts=} {material=}")

     # Convert and validate inputs
    amps = int(amps)
    meters = int(meters)
    volts = int(volts)
    max_lines = 1 if max_lines in (None, "") else int(max_lines)
    if max_awg in (None, ""):
        max_awg = None
    else:
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

    def _calc(*, force_awg=None, limit_awg=None):
        local_conduit = conduit
        with gw.sql.open_connection(autoload=True) as cursor:
            sql = (
                "SELECT awg_size, line_num, k_ohm_km, amps_60c, amps_75c, amps_90c "
                "FROM awg_cable_size "
                "WHERE (material = :material OR :material = '?') "
            )
            if force_awg is not None:
                sql += "AND awg_size = :awg_size "
            elif limit_awg is not None:
                sql += "AND awg_size >= :max_awg "
            sql += "AND line_num <= :max_lines ORDER BY awg_size DESC, line_num"

            params = {"material": material, "max_lines": max_lines}
            if force_awg is not None:
                params["awg_size"] = int(force_awg)
            elif limit_awg is not None:
                params["max_awg"] = int(limit_awg)
            gw.debug(f"AWG base data SQL: {sql.strip()}, params: {params}")
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            gw.debug(f"AWG base rows fetched: {rows}")

            awg_data = {}
            for awg_size, line_num, k_ohm, a60, a75, a90 in rows:
                awg_data.setdefault(awg_size, {})[line_num] = {
                    "k": k_ohm,
                    "a60": a60,
                    "a75": a75,
                    "a90": a90,
                }

            if phases in (2, 3):
                base_vdrop = math.sqrt(3) * meters * amps / 1000
            else:
                base_vdrop = 2 * meters * amps / 1000

            best = None
            best_perc = 1e9

            if force_awg is not None:
                sizes = [int(force_awg)] if int(force_awg) in awg_data else []
            elif limit_awg is None:
                sizes = sorted(awg_data.keys(), reverse=True)
            else:
                sizes = sorted([s for s in awg_data.keys() if s >= int(limit_awg)])

            for awg_size in sizes:
                base = awg_data[awg_size][1]
                for n in range(1, max_lines + 1):
                    info = awg_data[awg_size].get(n)
                    a60 = (info or base)["a60"] if info else base["a60"] * n
                    a75 = (info or base)["a75"] if info else base["a75"] * n
                    a90 = (info or base)["a90"] if info else base["a90"] * n
                    if temperature is None:
                        allowed = ((a75 >= amps and amps > 100) or (a60 >= amps and amps <= 100))
                    else:
                        tmap = {60: a60, 75: a75, 90: a90}
                        allowed = tmap.get(temperature, 0) >= amps
                    if not allowed and force_awg is None:
                        continue

                    vdrop = base_vdrop * base["k"] / n
                    perc = vdrop / volts
                    gw.debug(
                        f"Eval AWG={awg_size} lines={n} drop={vdrop:.4f} perc={perc*100:.4f}%"
                    )
                    result = {
                        "awg": str(AWG(awg_size)),
                        "meters": meters,
                        "amps": amps,
                        "volts": volts,
                        "temperature": temperature if temperature is not None else (60 if amps <= 100 else 75),
                        "lines": n,
                        "vdrop": vdrop,
                        "vend": volts - vdrop,
                        "vdperc": perc * 100,
                        "cables": f"{n * phases}+{n * ground}",
                        "total_meters": f"{n * phases * meters}+{meters * n * ground}",
                    }
                    if force_awg is None:
                        if allowed and perc <= 0.03:
                            if local_conduit:
                                c = "emt" if local_conduit is True else local_conduit
                                fill = find_conduit(AWG(awg_size), n * (phases + ground), conduit=c)
                                result["conduit"] = c
                                result["pipe_inch"] = fill["size_inch"]
                            gw.debug(f"Selected cable result: {result}")
                            return result
                        if perc < best_perc:
                            best = result
                            best_perc = perc
                    else:
                        if allowed and perc <= 0.03:
                            if local_conduit:
                                c = "emt" if local_conduit is True else local_conduit
                                fill = find_conduit(AWG(awg_size), n * (phases + ground), conduit=c)
                                result["conduit"] = c
                                result["pipe_inch"] = fill["size_inch"]
                            gw.debug(f"Selected cable result: {result}")
                            return result
                        if perc < best_perc:
                            best = result
                            best_perc = perc

            if best and (force_awg is not None or limit_awg is not None):
                if force_awg is not None:
                    best["warning"] = "Voltage drop may exceed 3% with chosen parameters"
                else:
                    best["warning"] = "Voltage drop exceeds 3% with given max_awg"
                if local_conduit:
                    c = "emt" if local_conduit is True else local_conduit
                    fill = find_conduit(AWG(best["awg"]), best["lines"] * (phases + ground), conduit=c)
                    best["conduit"] = c
                    best["pipe_inch"] = fill["size_inch"]
                gw.debug(f"Returning best effort with warning: {best}")
                return best

            gw.debug("No candidate meets requirements")
            return {"awg": "n/a"}

    baseline = _calc()
    if max_awg is None:
        return baseline

    if baseline.get("awg") == "n/a":
        return _calc(limit_awg=max_awg)

    if int(AWG(baseline["awg"])) < int(max_awg):
        return _calc(force_awg=max_awg)
    return _calc(limit_awg=max_awg)


def find_conduit(awg, cables, *, conduit="emt"):
    """Calculate the kind of conduit required for a set of cables."""
    with gw.sql.open_connection(autoload=True) as cursor:

        assert conduit in ("emt", "imc", "rmc", "fmc"), "Allowed: emt, imc, rmc, fmc."
        assert 1 <= cables <= 30, "Valid for 1-30 cables per conduit."

        awg = AWG(awg)
        col = f"awg_{str(awg)}"
        sql = f"""
            SELECT trade_size, {col}
            FROM awg_conduit_fill
            WHERE lower(conduit) = lower(:conduit)
            AND {col} >= :cables
        """

        cursor.execute(sql, {"conduit": conduit, "cables": cables})
        rows = cursor.fetchall()
        if not rows:
            return {"size_inch": "n/a"}

        def _to_float(value: str) -> float:
            total = 0.0
            for part in value.split():
                if "/" in part:
                    num, den = part.split("/")
                    total += float(num) / float(den)
                else:
                    total += float(part)
            return total

        rows.sort(key=lambda r: _to_float(r[0]))
        size, capacity = rows[0]
        if capacity == cables and len(rows) > 1:
            size = rows[1][0]

        return {"size_inch": size}


def view_awg_calculator(
    *, meters=None, amps="40", volts="220", material="cu",
    max_lines="1", max_awg=None, phases="1", temperature=None,
    conduit=None, ground="1", neutral="0", **kwargs
):
    """Page builder for AWG calculator with HTML form and result."""
    if not meters:
        return '''<link rel="stylesheet" href="/static/awg/cable_finder.css">
            <h1>Cable & Conduit Calculator</h1>
            <form method="post" class="cable-form">
                <table class="form-table two-col">
                    <tr>
                        <td>
                            <label for="meters">Meters:</label>
                            <input id="meters" type="number" name="meters" required min="1" />
                        </td>
                        <td>
                            <label for="amps">Amps:</label>
                            <input id="amps" type="number" name="amps" value="40" />
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <label for="volts">Volts:</label>
                            <input id="volts" type="number" name="volts" value="220" />
                        </td>
                        <td>
                            <label for="material">Material:</label>
                            <select id="material" name="material">
                                <option value="cu">Copper (cu)</option>
                                <option value="al">Aluminum (al)</option>
                            </select>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <label for="phases">Phases:</label>
                            <select id="phases" name="phases">
                                <option value="2">AC Two Phases (2)</option>
                                <option value="1">AC Single Phase (1)</option>
                                <option value="3">AC Three Phases (3)</option>
                            </select>
                        </td>
                        <td>
                            <label for="temperature">Temperature:</label>
                            <select id="temperature" name="temperature">
                                <option value="auto">Auto</option>
                                <option value="60">60C</option>
                                <option value="75">75C</option>
                                <option value="90">90C</option>
                            </select>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <label for="conduit">Conduit:</label>
                            <select id="conduit" name="conduit">
                                <option value="emt" selected>EMT</option>
                                <option value="imc">IMC</option>
                                <option value="rmc">RMC</option>
                                <option value="fmc">FMC</option>
                                <option value="none">None</option>
                            </select>
                        </td>
                        <td>
                            <label for="max_awg">Max AWG:</label>
                            <input id="max_awg" type="text" name="max_awg" />
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <label for="ground">Ground:</label>
                            <select id="ground" name="ground">
                                <option value="1" selected>1</option>
                                <option value="0">0</option>
                            </select>
                        </td>
                        <td>
                            <label for="max_lines">Max Lines:</label>
                            <select id="max_lines" name="max_lines">
                                <option value="1">1</option>
                                <option value="2">2</option>
                                <option value="3">3</option>
                                <option value="4">4</option>
                            </select>
                        </td>
                    </tr>
                </table>
                <button type="submit" class="submit">Calculate</button>
            </form>
        '''
    if max_awg in (None, ""):
        max_awg = None
    if conduit in (None, "", "none", "None"):
        conduit_arg = None
    else:
        conduit_arg = conduit
    try:
        result = find_awg(
            meters=meters, amps=amps, volts=volts,
            material=material,
            max_lines=max_lines, phases=phases,
            max_awg=max_awg, temperature=temperature,
            conduit=conduit_arg, ground=ground,
        )
    except Exception as e:
        return f"<p class='error'>Error: {e}</p><p><a href='/awg/awg-calculator'>&#8592; Try again</a></p>"

    if result.get("awg") == "n/a":
        return """
            <h1>No Suitable Cable Found</h1>
            <p>No cable was found that meets the requirements within a 3% voltage drop.<br>
            Try adjusting the <b>cable size, amps, length, or material</b> and try again.</p>
            <p><a href="/awg/awg-calculator">&#8592; Calculate again</a></p>
        """

    return f"""
        <div class='calc-result'>
        <h1>AWG Cable & Conduit Results <img src='/static/awg/sponsor_logo.svg' alt='Sponsor Logo' class='sponsor-logo'></h1>
        <ul class='result-list'>
            <li><strong>AWG Size:</strong> {result['awg']}</li>
            <li><strong>Lines:</strong> {result['lines']}</li>
            <li><strong>Total Cables:</strong> {result['cables']}</li>
            <li><strong>Total Length (m):</strong> {result['total_meters']}</li>
            <li><strong>Voltage Drop:</strong> {result['vdrop']:.2f} V ({result['vdperc']:.2f}%)</li>
            <li><strong>Voltage at End:</strong> {result['vend']:.2f} V</li>
            <li><strong>Temperature Rating:</strong> {result['temperature']}C</li>
            {f'<li><strong>Conduit:</strong> {result["conduit"].upper()} {result["pipe_inch"]}&quot;</li>' if result.get("pipe_inch") else ''}
        </ul>
        {f"<p class='warning'>{result['warning']}</p>" if result.get('warning') else ''}
        <p>
        <em>Special thanks to the expert engineers at <strong>
        <a href="https://www.gelectriic.com" target="_blank">Gelectriic Solutions</a></strong> for their
        support in creating this calculator.</em>
        </p>
        <p><a href="/awg/awg-calculator">&#8592; Calculate again</a></p>
        </div>
    """
