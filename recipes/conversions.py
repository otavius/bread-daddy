"""
recipes/conversions.py
 
Pure-Python unit conversion, recipe scaling, and baker's percentage helpers.
 
Design rules:
  * No Django imports and no database calls, so everything is easy to unit test.
  * All math uses Decimal (never float) to avoid rounding drift.
  * Every unit converts through a base unit: grams for weight, millilitres for
    volume. Weight <-> volume needs a density (grams per millilitre).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from typing import Iterable, Mapping, Optional, Union 

Number = Union[int, float, str, Decimal]

 
# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConversionError(ValueError):
    """Base class for all converson problems."""


class UnknownUnitError(ConversionError):
    """The unit string isn't recognosed."""

class IncompatibleUnitsError(ConversionError):
    """The units can't be converted (e.g. eggs to grams)."""    

class MissingDensityError(ConversionError):
    """A weight ,-. volume conversion was requestes without a density."""

class NoFlourError(ConversionError):
    """Baker's percentages need at least one flour with a non-zero weight."""

# ---------------------------------------------------------------------------
# Unit definitions
# ---------------------------------------------------------------------------

WEIGHT = "weight"
VOLUME = "volume"
COUNT = "count"

@dataclass(frozen=True)
class Unit: 
    name: str # canonical short name, e.g. "g"
    dimension: str # WEIGHT, VOLUME or COUNT
    factor: Decimal # how many base units (g/ ml/ each) in one of this unit


def _u(name: str, dimension: str, factor: str) -> Unit:
    return Unit(name, dimension, Decimal(factor))


# US customary volume units, metric weight/volume, avoirdupois weight.
UNITS: dict[str, Unit] = {
    u.name: u
    for u in [
        # weight (base: gram)
        _u("g", WEIGHT, "1"),
        _u("kg", WEIGHT, "1000"),
        _u("mg", WEIGHT, "0.001"),
        _u("oz", WEIGHT, "28.349523125"),
        _u("lb", WEIGHT, "453.59237"),
        # volume (base: millilitre)
        _u("ml", VOLUME, "1"),
        _u("l", VOLUME, "1000"),
        _u("tsp", VOLUME, "4.92892159375"),
        _u("tbsp", VOLUME, "14.78676478125"),
        _u("fl_oz", VOLUME, "29.5735295625"),
        _u("cup", VOLUME, "236.5882365"),
        _u("pint", VOLUME, "473.176473"),
        _u("quart", VOLUME, "946.352946"),
        _u("gallon", VOLUME, "3785.411784"),
        # count (base: each)
        _u("each", COUNT, "1"),
        _u("dozen", COUNT, "12"),
    ]
}
 
# Friendly spellings people will type or import.
_ALIASES: dict[str, str] = {
    "gram": "g", "grams": "g", "gr": "g",
    "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "milligram": "mg", "milligrams": "mg",
    "ounce": "oz", "ounces": "oz",
    "pound": "lb", "pounds": "lb", "lbs": "lb",
    "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "teaspoon": "tsp", "teaspoons": "tsp", "tsps": "tsp", "t": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsps": "tbsp", "tbs": "tbsp", "tbl": "tbsp",
    "fl oz": "fl_oz", "floz": "fl_oz", "fluid ounce": "fl_oz", "fluid ounces": "fl_oz",
    "cups": "cup", "c": "cup",
    "pints": "pint", "pt": "pint",
    "quarts": "quart", "qt": "quart",
    "gallons": "gallon", "gal": "gallon",
    "ea": "each", "piece": "each", "pieces": "each", "pc": "each", "pcs": "each",
    "dozens": "dozen", "doz": "dozen",
}
 
# One US cup in millilitres, used to turn "grams per cup" into a density.
ML_PER_CUP = UNITS["cup"].factor
 
 
def get_unit(unit: str) -> Unit:
    """Look up a unit by canonical name or alias (case-insensitive)."""
    key = unit.strip().lower()
    key = _ALIASES.get(key, key)
    try:
        return UNITS[key]
    except KeyError:
        raise UnknownUnitError(f"Unknown unit: {unit!r}") from None
 
 
def normalize_unit(unit: str) -> str:
    """Return the canonical short name for a unit, e.g. 'Tablespoons' -> 'tbsp'."""
    return get_unit(unit).name
 
 
def unit_choices() -> list[tuple[str, str]]:
    """(value, label) pairs, handy for Django model/form `choices=`."""
    return [(name, name) for name in UNITS]
 
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
 
def to_decimal(value: Number) -> Decimal:
    """Convert to Decimal safely (floats go through str to avoid binary noise)."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        raise ConversionError(f"Not a valid number: {value!r}") from None
 
 
def density_from_grams_per_cup(grams_per_cup: Number) -> Decimal:
    """Convert an ingredient's 'grams per US cup' into grams per millilitre."""
    gpc = to_decimal(grams_per_cup)
    if gpc <= 0:
        raise ConversionError("grams_per_cup must be greater than zero")
    return gpc / ML_PER_CUP
 
 
# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------
 
 
def convert(
    quantity: Number,
    from_unit: str,
    to_unit: str,
    grams_per_ml: Optional[Number] = None,
) -> Decimal:
    """
    Convert `quantity` from one unit to another.
 
    Same-dimension conversions (g -> oz, cup -> ml) need no extra info.
    Weight <-> volume conversions need `grams_per_ml` (the ingredient density).
    """
    q = to_decimal(quantity)
    src, dst = get_unit(from_unit), get_unit(to_unit)
 
    if src.dimension == dst.dimension:
        return q * src.factor / dst.factor
 
    if COUNT in (src.dimension, dst.dimension):
        raise IncompatibleUnitsError(
            f"Cannot convert between {src.name!r} and {dst.name!r}"
        )
 
    if grams_per_ml is None:
        raise MissingDensityError(
            f"Converting {src.name} to {dst.name} needs the ingredient's density"
        )
    density = to_decimal(grams_per_ml)
    if density <= 0:
        raise ConversionError("Density must be greater than zero")
 
    base = q * src.factor
    if src.dimension == VOLUME:       # ml -> g
        base = base * density
    else:                             # g -> ml
        base = base / density
    return base / dst.factor
 
 
def to_grams(quantity: Number, unit: str, grams_per_ml: Optional[Number] = None) -> Decimal:
    """Shortcut: convert any weight or volume to grams."""
    return convert(quantity, unit, "g", grams_per_ml)
 
 
# ---------------------------------------------------------------------------
# Rounding and display
# ---------------------------------------------------------------------------
 
 
def round_decimal(value: Number, places: int = 2) -> Decimal:
    """Round half-up (what people expect), not banker's rounding."""
    exp = Decimal(1).scaleb(-places)
    return to_decimal(value).quantize(exp, rounding=ROUND_HALF_UP)
 
 
def to_fraction_string(value: Number, denominator: int = 8) -> str:
    """
    Format as a kitchen fraction, e.g. 1.5 -> '1 1/2', 0.75 -> '3/4'.
    Rounds to the nearest 1/denominator.
    """
    q = to_decimal(value)
    whole = int(q)
    steps = ((q - whole) * denominator).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if steps >= denominator:
        whole += 1
        steps = Decimal(0)
    frac = Fraction(int(steps), denominator)
    if frac == 0:
        return str(whole)
    frac_str = f"{frac.numerator}/{frac.denominator}"
    return frac_str if whole == 0 else f"{whole} {frac_str}"
 
 
_FRACTION_UNITS = {"cup", "tbsp", "tsp", "pint", "quart", "gallon", "fl_oz"}
 
 
def format_quantity(value: Number, unit: str) -> str:
    """
    Human-friendly quantity string.
      * cups/spoons -> fractions ("1 1/2 cup")
      * grams/ml    -> whole numbers when large, one decimal when small
      * everything else -> up to 2 decimals, trailing zeros trimmed
    """
    u = get_unit(unit)
    q = to_decimal(value)
 
    if u.name in _FRACTION_UNITS:
        text = to_fraction_string(q)
    elif u.name in {"g", "ml"}:
        text = str(round_decimal(q, 0 if q >= 10 else 1).normalize())
    else:
        text = str(round_decimal(q, 2).normalize())
    # normalize() can yield scientific notation for round numbers like 1E+2
    if "E" in text:
        text = format(Decimal(text), "f")
    return f"{text} {u.name}"
 
 
# ---------------------------------------------------------------------------
# Recipe lines and scaling
# ---------------------------------------------------------------------------
 
 
@dataclass(frozen=True)
class IngredientLine:
    """
    A plain-data view of a recipe ingredient, decoupled from Django models.
    Build these from RecipeIngredient rows in your service layer.
    """
    name: str
    quantity: Decimal
    unit: str
    grams_per_ml: Optional[Decimal] = None   # density, if known
    is_flour: bool = False                   # counts toward baker's 100%
 
 
def scale_factor(current_yield: Number, target_yield: Number) -> Decimal:
    """Multiplier needed to turn a recipe making `current_yield` into `target_yield`."""
    cur, tgt = to_decimal(current_yield), to_decimal(target_yield)
    if cur <= 0:
        raise ConversionError("Current yield must be greater than zero")
    if tgt <= 0:
        raise ConversionError("Target yield must be greater than zero")
    return tgt / cur
 
 
def scale_lines(lines: Iterable[IngredientLine], factor: Number) -> list[IngredientLine]:
    """Return new lines with every quantity multiplied by `factor`."""
    f = to_decimal(factor)
    if f <= 0:
        raise ConversionError("Scale factor must be greater than zero")
    return [replace(line, quantity=line.quantity * f) for line in lines]
 
 
def scale_to_yield(
    lines: Iterable[IngredientLine], current_yield: Number, target_yield: Number
) -> list[IngredientLine]:
    """Scale a whole recipe from one yield to another."""
    return scale_lines(lines, scale_factor(current_yield, target_yield))
 
 
def convert_lines(
    lines: Iterable[IngredientLine],
    to_unit: str,
    *,
    skip_unconvertible: bool = True,
) -> list[IngredientLine]:
    """
    Convert every line to `to_unit`. Lines that can't convert (counts like eggs,
    or weight<->volume with no density) are left unchanged when
    `skip_unconvertible` is True, otherwise the error is raised.
    """
    out: list[IngredientLine] = []
    for line in lines:
        try:
            new_q = convert(line.quantity, line.unit, to_unit, line.grams_per_ml)
            out.append(replace(line, quantity=new_q, unit=normalize_unit(to_unit)))
        except (IncompatibleUnitsError, MissingDensityError):
            if not skip_unconvertible:
                raise
            out.append(line)
    return out
 
 
# ---------------------------------------------------------------------------
# Baker's percentages
# ---------------------------------------------------------------------------
 
 
def line_grams(line: IngredientLine) -> Decimal:
    """Weight of a line in grams (uses the line's density for volume units)."""
    return to_grams(line.quantity, line.unit, line.grams_per_ml)
 
 
def total_flour_grams(lines: Iterable[IngredientLine]) -> Decimal:
    total = sum((line_grams(l) for l in lines if l.is_flour), Decimal(0))
    if total <= 0:
        raise NoFlourError("Recipe has no flour weight to base percentages on")
    return total
 
 
def bakers_percentages(lines: Iterable[IngredientLine]) -> dict[str, Decimal]:
    """
    Each ingredient's weight as a percentage of total flour weight.
    Total flour = 100%. Count-only lines (eggs with no weight) are skipped.
    """
    lines = list(lines)
    flour = total_flour_grams(lines)
    result: dict[str, Decimal] = {}
    for line in lines:
        try:
            grams = line_grams(line)
        except ConversionError:
            continue
        result[line.name] = result.get(line.name, Decimal(0)) + grams / flour * 100
    return result
 
 
def grams_from_bakers_percentages(
    percentages: Mapping[str, Number], total_flour_g: Number
) -> dict[str, Decimal]:
    """
    Reverse direction: given percentages and a total flour weight, return grams
    per ingredient. Great for 'I have 5 kg of flour, what do I need?'
    """
    flour = to_decimal(total_flour_g)
    if flour <= 0:
        raise ConversionError("Total flour weight must be greater than zero")
    return {name: to_decimal(p) / 100 * flour for name, p in percentages.items()}
 
 
def hydration(lines: Iterable[IngredientLine], liquid_names: Iterable[str]) -> Decimal:
    """Hydration % = weight of the named liquids / total flour weight * 100."""
    lines = list(lines)
    flour = total_flour_grams(lines)
    liquids = {n.lower() for n in liquid_names}
    liquid_g = sum(
        (line_grams(l) for l in lines if l.name.lower() in liquids), Decimal(0)
    )
    return liquid_g / flour * 100