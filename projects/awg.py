# projects/awg.py

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
    meters: Union[int, str, None] = None,
    amps: Union[int, str] = "40",
    volts: Union[int, str] = "220",
    material: Literal["cu", "al", "?"] = "cu",
    max_lines: Union[int, str] = "1",
    phases: Literal["1", "3", 1, 3] = "1",
    conduit: Optional[Union[str, bool]] = None,
    neutral: Union[int, str] = "1"
):
    """Calculate the type of cable needed for an electrical system."""
    gw.info(f"Calculating AWG for {meters=} {amps=} {volts=} {material=}")
    
    with gw.sql.open_connection(autoload=True) as cursor:
        # Convert inputs
        amps = int(amps)
        meters = int(meters)
        volts = int(volts)
        max_lines = int(max_lines)
        phases = int(phases)
        neutral = int(neutral)

        # Validate inputs
        assert amps >= 20, "Min. charger load is 20 Amps."
        assert meters >= 1, "Consider at least 1 meter of cable."
        assert 110 <= volts <= 460, "Volt range is 110-460."
        assert material in ("cu", "al", "?"), "Material must be cu, al or ?."
        assert phases in (1, 3), "Allowed phases 1 or 3."

        # Choose voltage drop formula based on phases
        if phases == 3:
            expr = "sqrt(3) * (:meters / line_num) * (k_ohm_km / 1000)"
        else:
            expr = "2 * (:meters / line_num) * (k_ohm_km / 1000)"

        # Fetch all ampacity-qualified cables ordered by AWG descending (largest cable first)
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
                cables = line_num * (phases + neutral)
                result = {
                    "awg": str(awg_res),
                    "amps": amps,
                    "meters": meters,
                    "lines": line_num,
                    "vdrop": vdrop,
                    "vend": volts - vdrop,
                    "vdperc": perc * 100,
                    "cables": cables,
                    "cable_m": cables * meters,
                }
                if conduit:
                    if conduit is True:
                        conduit = "emt"
                    fill = find_conduit(awg_res, cables, conduit=conduit)
                    result["conduit"] = conduit
                    result["pipe_in"] = fill["size_in"]

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

        return {
            "size_in": row[0]
        }
