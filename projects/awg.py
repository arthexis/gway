import logging
from typing import Literal, Union, Optional
from gway import gw


class AWG(int):
    def __new__(cls, value):
        if isinstance(value, str) and "/" in value:
            # Convert '1/0', '2/0', etc. to -1, -2, ...
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
        max_lines: Union[int, str] = "3",
        phases: Literal["1", "3", 1, 3] = "1",
        conduit: Optional[Union[str, bool]] = None,
        neutral: Union[int, str] = "0"
    ):
    """Calculate the type of cable needed for an electrical system."""
    with gw.database.connect(load_data="awg") as cursor:
            
        amps = int(amps)
        meters = int(meters)
        volts = int(volts)
        max_lines = int(max_lines)
        phases = int(phases)
        neutral = int(neutral)
        
        assert amps >= 40, "Min. charger load is 20 Amps."
        assert meters >= 1, "Consider at least 1 meter of cable."
        assert 110 <= volts <= 460, "Volt range is 110-460."
        assert material in ("cu", "al", "?"), "Material must be cu, al or ?."
        assert phases in (1, 3), "Allowed phases 1 or 3."
        
        if phases == 3:
            formula = "sqrt(3) * (:meters / line_num) * (k_ohm_km / 1000)"
        else:
            formula = "2 * (:meters / line_num) * (k_ohm_km / 1000)"
        
        sql = f"""
            SELECT awg_size, line_num, {formula} AS vdrop
            FROM awg_cable_size
            WHERE (material = :material OR :material = '?')  
            AND ((amps_75c >= :amps AND :amps > 100) 
            OR (amps_60c >= :amps AND :amps <= 100))
            AND ({formula}) / :volts <= 0.03
            AND line_num <= :max_lines
            ORDER BY line_num ASC, awg_size DESC LIMIT 1;
        """
        
        params = {
            "amps": amps,
            "meters": meters,
            "material": material,
            "volts": volts,
            "max_lines": max_lines
        }

        gw.debug(f"AWG find-cable SQL: {sql}, params: {params}")
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if not row:
            return {"awg": "n/a"}
        
        awg_result = AWG(row[0])
        cables = row[1] * (phases + neutral)
        result = {
            "awg": str(awg_result),
            "amps": amps,
            "meters": meters,
            "lines": row[1],
            "vdrop": row[2],
            "vend": volts - row[2],
            "vdperc": row[2] / volts * 100,
            "cables": cables,
            "cable_m": int(cables) * meters,
        }

        if conduit:
            if conduit is True:
                conduit = "emt"
            fill = find_conduit(awg_result, cables, conduit=conduit)
            result["conduit"] = conduit
            result["pipe_in"] = fill["size_in"]
        return result


def find_conduit(awg, cables, conduit="emt"):
    """Calculate the kind of conduit required for a set of cables."""
    with gw.database.connect(load_data="awg") as cursor:

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
