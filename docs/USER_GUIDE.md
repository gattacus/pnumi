# Pnumi User Guide

Pnumi is a natural language calculator designed to help you write calculations as plain text and get instant inline results. It combines the flexibility of a text editor with the power of a symbolic calculator, handling units, currencies, percentages, dates, times, and mathematical functions.

This guide details the core capabilities of the Pnumi calculation engine, with a particular focus on its rich, "invisible" features.

---

## Table of Contents

- [Basic Calculations](#basic-calculations)
  - [Arithmetic Operations](#arithmetic-operations)
  - [Alternate Number Bases](#alternate-number-bases)
  - [Scientific Notation](#scientific-notation)
  - [Number Formatting](#number-formatting)
- [Variables and Context](#variables-and-context)
  - [Declaring Variables](#declaring-variables)
  - [The prev Keyword](#the-prev-keyword)
  - [Aggregating Rows: sum and average](#aggregating-rows-sum-and-average)
- [Comments and Formatting](#comments-and-formatting)
  - [Comments and Ignored Text](#comments-and-ignored-text)
  - [Document Headers](#document-headers)
  - [Labels](#labels)
- [Percentages](#percentages)
  - [Percentage Calculations](#percentage-calculations)
  - [Variables with Percentages](#variables-with-percentages)
- [Units and Conversions](#units-and-conversions)
  - [Conversion Syntax](#conversion-syntax)
  - [Supported Units](#supported-units)
  - [SI Prefixes and Scale Suffixes](#si-prefixes-and-scale-suffixes)
  - [Compound and Derived Units](#compound-and-derived-units)
  - [Dynamic CSS Scaling (ppi and em)](#dynamic-css-scaling-ppi-and-em)
- [Currency Support](#currency-support)
  - [Rate Provider and Yahoo Finance](#rate-provider-and-yahoo-finance)
  - [ISO Currency Codes and Names](#iso-currency-codes-and-names)
  - [Cryptocurrencies](#cryptocurrencies)
  - [Mixed Currency Arithmetic](#mixed-currency-arithmetic)
- [Mathematical Functions](#mathematical-functions)
  - [Standard Arithmetic Functions](#standard-arithmetic-functions)
  - [Trigonometric Functions](#trigonometric-functions)
- [Date and Time Operations](#date-and-time-operations)
  - [Current Date and Time](#current-date-and-time)
  - [Timezone Operations](#timezone-operations)
  - [Date Arithmetic](#date-arithmetic)
  - [Unix Timestamp Conversion](#unix-timestamp-conversion)
- [Keyboard Shortcuts and UI Interaction](#keyboard-shortcuts-and-ui-interaction)

---

## Basic Calculations

Pnumi evaluates expressions line-by-line. The editor is split: you type your calculations on the left, and Pnumi displays the formatted results on the right.

### Arithmetic Operations

Standard arithmetic operators are supported. You can use standard symbols or equivalent natural language words:

- **Addition**: `+`, `plus`, `and`, `with`
- **Subtraction**: `-`, `minus`, `subtract`, `without`
- **Multiplication**: `*`, `times`, `mul`, `multiplied by`
- **Division**: `/`, `divide`, `divide by`
- **Exponentiation**: `^`
- **Modulo**: `%`, `mod`
- **Bitwise Operations**: `xor` (bitwise XOR), `&` (bitwise AND), `|` (bitwise OR)

Example expressions:

```text
2 plus 3 multiplied by 4  # 14
100 subtract 25           # 75
12 divide by 4            # 3
2 ^ 8                     # 256
2 xor 3                   # 1
12 & 25                   # 8
12 | 25                   # 29
```

Pnumi also supports **implicit multiplication** when parentheses are used without an explicit operator:

```text
6 (3)                     # 18
2 (5 + 5)                 # 20
```

### Alternate Number Bases

Pnumi allows inputting and displaying numbers in binary, octal, and hexadecimal formats. You can mix bases in a single expression and convert between them using the conversion syntax (`in`, `to`, `into`, or `as`):

- **Binary**: Prefixed with `0b`
- **Octal**: Prefixed with `0o`
- **Hexadecimal**: Prefixed with `0x`

Example calculations:

```text
0b110111011               # 443
0o1435343 in hex          # 0x63ae3
0x2a + 0b10               # 44
256 in binary             # 0b100000000
```

### Scientific Notation

You can display any expression's result in scientific notation by adding the `scientific` or `sci` keyword at the end of the line:

```text
5 300 scientific          # 5.3000000000e3
1000000000 sci            # 1.0000000000e9
```

### Number Formatting

Pnumi parses numbers with various thousand separators, including spaces, commas, and single quotes. The formatting of the result reflects the input's style:

```text
1'000 + 2                 # 1'002
1,000,000 * 2             # 2'000'000
1 500.50 + 500            # 2'000.5
```

---

## Variables and Context

You can define variables to reuse calculated values throughout a document.

### Declaring Variables

Define a variable by assigning a value or expression to a name. Names must start with a letter or underscore, followed by alphanumeric characters or underscores:

```text
hourly_rate = 50 EUR      # 50 EUR
hours_worked = 40         # 40
total_earnings = hourly_rate * hours_worked # 2'000 EUR
```

If you redefine a variable, subsequent lines will use the updated value.

### The prev Keyword

The `prev` keyword acts as a special variable that references the result of the immediately preceding calculated line. This is useful for chain calculations without naming intermediate results:

```text
$150                      # 150 USD
prev - 20                 # 130 USD
prev * 2                  # 260 USD
```

### Aggregating Rows: sum and average

Pnumi provides aggregate functions to sum or average the results of the current document section:

- `sum` or `total`: Adds all calculated line values in the current section.
- `average` or `avg`: Calculates the mean of all calculated line values in the current section.

You can direct aggregates into a specific target unit or currency:

```text
$10                       # 10 USD
$20                       # 20 USD
$30                       # 30 USD
sum in USD                # 60 USD
```

You can also continue aggregate expressions with arithmetic tails:

```text
$10
$20
$30
sum - 10%                 # 54 USD

$10
$20
$30
total in EUR + 5 EUR      # 59 EUR

$10
$20
$30
average * 2               # 40 USD
```

---

## Comments and Formatting

Pnumi offers markdown-like options to document your calculations without affecting the calculation engine.

### Comments and Ignored Text

- **Single-line comments**: Begin a line with `#` or `//`. The entire line is ignored.
- **Inline comments**: Anything following `//` on a line is treated as a comment and ignored.
- **Inline annotations**: Text enclosed in double quotes `""` is treated as descriptive text and stripped out of the expression before evaluation.

```text
# This is a full line comment
// This is also a comment
10 USD "for lunch" + 20 USD "for dinner"  # 30 USD
```

### Document Headers

Lines starting with markdown headers (like `#` or `##`) are treated as comment lines. However, they are also visually distinct and help organize your calculations into sections.

### Labels

If a line starts with a word followed by a colon (e.g. `Label: expression`), Pnumi treats the label as ignored annotation text and evaluates only the expression on the right:

```text
Subtotal: 10 USD + 15 USD # 25 USD
```

---

## Percentages

Percentages are natively supported by Pnumi and are treated as distinct values.

### Percentage Calculations

Pnumi provides natural language structures for percentage calculations:

- **Percentage of**: `x% of y` (computes `y * (x / 100)`)
- **Percentage add-on**: `x% on y` (computes `y * (1 + x / 100)`)
- **Percentage discount**: `x% off y` (computes `y * (1 - x / 100)`)
- **Determine percentage**: `a as a % of b` (computes `(a / b) * 100`)
- **Determine markup percentage**: `a as a % on b` (computes `((a / b) - 1) * 100`)
- **Determine markdown percentage**: `a as a % off b` (computes `(1 - (a / b)) * 100`)
- **Reverse percentage of**: `x% of what is y` (computes `y / (x / 100)`)
- **Reverse percentage on**: `x% on what is y` (computes `y / (1 + x / 100)`)
- **Reverse percentage off**: `x% off what is y` (computes `y / (1 - x / 100)`)

Examples:

```text
20% of $100               # 20 USD
5% on $30                 # 31.5 USD
6% off 40 EUR             # 37.6 EUR
$50 as a % of $100        # 50 %
5% of what is 20 USD      # 400 USD
```

### Variables with Percentages

You can assign percentage values to variables and use them in standard arithmetic. Pnumi applies percentage operators contextually:

```text
discount = 5%             # 5 %
price = 1000 EUR          # 1'000 EUR
price - discount          # 950 EUR
```

---

## Units and Conversions

Pnumi supports a wide array of physical units, unit conversions, and unit algebra.

### Conversion Syntax

Convert a value to another unit using the conversion keywords: `in`, `to`, `into`, or `as`.

```text
1 meter in cm             # 100 cm
12 pt in px               # 16 px
1 month in days           # 30.4166666667 day
```

### Supported Units

Pnumi groups units into dimensions. Conversions are only valid between units in the same dimension:

| Dimension | Supported Units / Aliases |
| :--- | :--- |
| **Length** | `m` (meter, meters, metre, metres), `mm` (millimeter, millimeters), `cm` (centimeter, centimeters), `km` (kilometer, kilometers), `mil` (mils), `pt` (point, points), `line` (lines), `inch` (inches), `hand` (hands), `ft` (foot, feet), `yd` (yard, yards), `rod` (rods), `chain` (chains), `furlong` (furlongs), `mile` (miles), `cable` (cables), `nmi` (nautical mile, nautical miles), `league` (leagues) |
| **Area** | `m2` (sqm, square meter, square meters, square metre, square metres), `hectare` (hectares, ha), `are` (ares), `acre` (acres) |
| **Volume** | `m3` (cbm, cubic meter, cubic meters), `l` (liter, liters, litre, litres), `pint` (pints), `quart` (quarts), `gallon` (gallons), `tsp` (teaspoon, teaspoons), `tbsp` (tablespoon, tablespoons), `cup` (cups) |
| **Weight** | `g` (gram, grams), `kg` (kilogram, kilograms), `tonne` (tonnes), `carat` (carats), `centner` (centners), `lb` (pound, pounds), `stone` (stones), `oz` (ounce, ounces) |
| **Angle** | `rad` (radian, radians), `deg` (degree, degrees, °) |
| **Data** | `bit` (bits, b), `byte` (bytes, B), `kb` (kilobit, kilobits), `kB` (kilobyte, kilobytes, KB), `Kib` (kibibit, kibibits), `KiB` (kibibyte, kibibytes), `MB` (megabytes), `GB` (gigabytes) |
| **Duration** | `second` (sec, secs, s, seconds), `minute` (min, mins, minutes), `hour` (h, hr, hrs, hours), `day` (days), `week` (weeks), `month` (months), `year` (years) |
| **Temperature** | `K` (kelvin, kelvins), `C` (celsius, °c), `F` (fahrenheit, °f) |
| **CSS/Design** | `px` (pixel, pixels), `em` (ems) |

### SI Prefixes and Scale Suffixes

For **Length**, **Weight**, and **Data** dimensions, Pnumi automatically applies standard SI prefixes:

- `pico`, `nano`, `micro`, `milli`, `centi`, `kilo`, `mega`, `giga`

You can also use numeric scale suffixes for faster input:

- `k` or `thousand` (multiplies by 1,000)
- `M` or `million` (multiplies by 1,000,000)
- `billion` (multiplies by 1,000,000,000)

```text
5k                        # 5'000
2 million                 # 2'000'000
5 kilometer in m          # 5'000 m
2 kilogram in g           # 2'000 g
```

### Compound and Derived Units

Pnumi supports unit calculations that combine multiplication and division. Units can be combined, squared, cubed, or canceled out:

```text
10km / 2h                 # 5 km/h
speed = 10km / 2h         # 5 km/h
speed * 30min             # 2.5 km
(2 m)^2                   # 4 m^2
90km/h / 30km/h           # 3
1 m / 100 cm              # 1
```

### Dynamic CSS Scaling (ppi and em)

CSS units like `px` and `em` rely on layout metrics. You can dynamically adjust these conversion ratios by defining `ppi` (pixels per inch) or `em` (font size) variables in your document:

```text
ppi = 326                 # 326
1 cm in px                # 128.3464566929 px

em = 16                   # 16
12 pt in em               # 3.3958333333 em
```

---

## Currency Support

Pnumi offers extensive support for fiat and cryptocurrencies, complete with live exchange rates.

### Rate Provider and Yahoo Finance

By default, currency conversions utilize the Yahoo Finance rate provider (`yfinance` package). This pulls near-live exchange rates automatically when you perform conversions.

### ISO Currency Codes and Names

Pnumi recognizes standard three-letter ISO 4217 currency codes, symbols, and natural language names.

- **Symbols**: `$`, `€`, `£`, `¥`, `₹`, `₽`
- **Aliases**: `dollar`, `dollars`, `euro`, `euros`, `pound`, `pounds`, `yen`, `yuan`, `rupee`, `rupees`, `rouble`, `roubles`, `ruble`, `rubles`, `zloty`, `zlotys`, `krona`, `kronas`, `krone`, `kroner`, `swiss franc`, `swiss francs`

Examples:

```text
$30 in EUR                # 27 EUR
50 roubles in USD         # 0.6 USD
100 yen in CHF            # 0.55 CHF
₹2500 in USD              # 30 USD
```

### Cryptocurrencies

Popular cryptocurrencies are supported using their respective tickers and aliases:

- `ADA`, `AVAX`, `BCH`, `BNB`, `BTC` (bitcoin, bitcoins), `DOGE` (dogecoin, dogecoins), `DOT`, `ETH` (ethereum, ether), `LINK`, `LTC` (litecoin, litecoins), `MATIC`, `SOL` (solana), `TRX`, `USDC`, `USDT`, `XLM`, `XMR` (monero), `XRP`

Examples:

```text
1 BTC in USD              # 55'000 USD (based on provider rates)
2 ether in EUR            # 3'600 EUR (based on provider rates)
10 solana in USD          # 1'500 USD (based on provider rates)
```

### Mixed Currency Arithmetic

If you perform arithmetic operations on different currencies, Pnumi automatically converts the second operand's value to the first operand's currency:

```text
$10 + 5 EUR               # 15.5555555556 USD
$30 CAD + 5 USD           # 36.25 CAD
```

You can also combine currency units with time units to perform rate-based calculations:

```text
10 EUR / 2h               # 5 EUR/h
rate = 10 EUR / 2h         # 5 EUR/h
rate * 3                  # 15 EUR/h
10EUR/h * 30min           # 5 EUR
```

---

## Mathematical Functions

Pnumi provides standard mathematical helpers in both prefix format (e.g. `func value`) and wrapped parentheses format (e.g. `func(value)`).

### Standard Arithmetic Functions

- `sqrt`: Square root
- `cbrt`: Cube root
- `abs`: Absolute value
- `ln`: Natural logarithm
- `log`: Logarithm base 10 (e.g. `log 100`), or base specified as first argument (e.g. `log(2, 8)`)
- `root`: Root of custom degree, e.g. `root 3 (8)` or `root(3, 8)`
- `fact`: Factorial
- `round`: Rounds to the nearest integer
- `ceil`: Rounds up
- `floor`: Rounds down

Note that `round`, `ceil`, and `floor` preserve any attached units or currencies.

### Trigonometric Functions

Trigonometric functions accept values in radians. However, if you attach the `deg` (degree) unit, Pnumi automatically converts the value to radians:

- `sin`, `cos`, `tan`
- `arcsin`, `arccos`, `arctan`
- `sinh`, `cosh`, `tanh`

Examples:

```text
sin 90 deg                # 1
tan(pi / 4)               # 1
```

---

## Date and Time Operations

Pnumi can evaluate date-based arithmetic, timezone conversions, and Unix timestamps.

### Current Date and Time

- `today`: Evaluates to today's date.
- `now` or `time`: Evaluates to the current date and time.

### Timezone Operations

You can obtain the current time in another timezone or convert a date-time to a specific timezone:

- **Timezone aliases**: `utc`, `gmt`, `pst`, `pdt`, `new york`, `berlin`, `madrid`, `hkt`, `hong kong`, `london`, `zurich`

Examples:

```text
london time               # 2026-06-17 22:27:10 BST (example output)
time in new york          # 2026-06-17 17:27:10 EDT (example output)
2026-06-17 12:00 in pst   # 2026-06-17 05:00:00 PDT
```

### Date Arithmetic

Add or subtract duration units to/from date values:

```text
today + 2 weeks           # 2026-07-01 (assuming today is 2026-06-17)
now - 3 hours             # 2026-06-17 20:27:10 (example output)
today + 30 days           # 2026-07-17 (assuming today is 2026-06-17)
```

### Unix Timestamp Conversion

Convert standard Unix epoch timestamps to UTC date-times using the `fromunix` function:

```text
fromunix(1446587186)      # 2015-11-03 21:46:26 UTC
fromunix 1718620800       # 2024-06-17 10:40:00 UTC
```

---

## Keyboard Shortcuts and UI Interaction

Pnumi supports standard desktop keyboard shortcuts for editor control and layout features:

| Command | macOS Shortcut | Windows / Linux Shortcut |
| :--- | :--- | :--- |
| **New Tab** | `Cmd + T` | `Ctrl + T` |
| **Close Tab** | `Cmd + W` | `Ctrl + W` |
| **Import File** | `Cmd + O` | `Ctrl + O` |
| **Export File** | `Cmd + S` | `Ctrl + S` |
| **Print Sheet** | `Cmd + P` | `Ctrl + P` |
| **Copy Current Line Result** | `Cmd + Shift + C` | `Ctrl + Shift + C` |
| **Copy All Lines and Results** | `Alt + Cmd + C` | `Alt + Ctrl + C` |
| **Delete All Text** | `Alt + Cmd + Backspace` | `Alt + Ctrl + Backspace` |
| **Surround Selected Text with Parentheses** | `Cmd + Shift + 0` | `Ctrl + Shift + 9` or `Ctrl + Shift + 0` |
| **Show Autocomplete Suggestions** | `Cmd + Space` | `Ctrl + Space` |
| **Open Settings** | `Cmd + ,` | Standard Preferences shortcut |

### Additional UI Features

- **Tab Reordering**: Click and drag tabs in the tab bar to reorder them.
- **Close Tab via Mouse**: Middle-click anywhere on a tab's title to close it.
- **Tab Close Confirmation**: Closing a non-empty tab prompts a confirmation dialog to prevent accidental data loss.
- **Rename Tabs**: Double-click a tab's title to rename it.
- **Section Boundaries**: Section results are reset by blank lines, allowing separate `sum` and `avg` scopes in the same sheet.
- **Customizable Settings**: Access settings (`Cmd + ,` or from Edit menu) to configure:
  - **Font Size**: Configure the font size of the calculation editor and results pane.
  - **Alternating Row Background**: Toggle the striped row background.
  - **Theme**: Choose between Light, Dark, or system-matching themes.
  - **Result Decimal Places**: Set the maximum number of decimal places for calculated results.
