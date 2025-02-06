#!/usr/bin/env python3
import json
import sys
import numpy_financial as npf
from decimal import Decimal, ROUND_HALF_UP
import re
import math
import google.generativeai as genai
import os

# Configure Gemini
genai.configure(api_key='AIzaSyAeSZswx2CCRmLk4b5rCu-aH0qIBsH1zn4')
model = genai.GenerativeModel('gemini-2.0-flash-001')  # Use flash model for structured extraction

def round_currency(amount):
    """Round to 2 decimal places using banker's rounding"""
    if isinstance(amount, bool):
        return amount
    else:
        return float(Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def calculate_real_rate(nominal_rate, inflation_rate, frequency='annual', compound_type='discrete'):
    """Calculate real rate using Fisher Effect with enhanced features
    
    Args:
        nominal_rate: Nominal interest rate as decimal
        inflation_rate: Expected inflation rate as decimal
        frequency: Compounding frequency ('annual', 'semiannual', 'monthly', 'daily', 'continuous')
        compound_type: Type of compounding ('discrete' or 'continuous')
        
    Returns:
        Real interest rate as decimal
        
    Raises:
        ValueError: If rates are invalid or frequency/compound_type not supported
    """
    # Validate inputs
    if nominal_rate <= -1:
        raise ValueError("Nominal rate must be > -100%")
    if inflation_rate <= -1:
        raise ValueError("Inflation rate must be > -100%")
        
    # Handle continuous compounding
    if compound_type == 'continuous':
        # For continuous compounding: r_real = r_nominal - r_inflation
        return nominal_rate - inflation_rate
        
    # Convert rates to the same frequency if not annual
    if frequency != 'annual':
        nominal_rate = convert_rate(nominal_rate, 'annual', frequency)
        inflation_rate = convert_rate(inflation_rate, 'annual', frequency)
        
    # Calculate real rate using Fisher equation
    real_rate = (1 + nominal_rate) / (1 + inflation_rate) - 1
    
    # Handle deflation case (negative inflation)
    if inflation_rate < 0:
        sys.stderr.write("Warning: Negative inflation (deflation) detected\n")
        
    return real_rate

def convert_rate(rate, from_freq, to_freq, compound_type='discrete', day_count='actual/360'):
    """Convert interest rate between different payment frequencies"""
    freq_map = {
        'annual': 1,
        'semiannual': 2,
        'monthly': 12,
        'daily': 365,
        'continuous': float('inf')
    }
    
    day_count_map = {
        'actual/360': 360,
        'actual/365': 365,
        'actual/actual': 365.25,
        '30/360': 360
    }
    
    # Validate inputs
    if rate <= -1:
        raise ValueError("Rate must be > -100%")
    
    if from_freq not in freq_map or to_freq not in freq_map:
        raise ValueError(f"Invalid frequency. Must be one of: {list(freq_map.keys())}")
        
    if day_count not in day_count_map:
        raise ValueError(f"Invalid day count convention. Must be one of: {list(day_count_map.keys())}")
        
    if compound_type not in ['discrete', 'continuous']:
        raise ValueError("Compound type must be 'discrete' or 'continuous'")
        
    if from_freq == to_freq:
        return rate
    
    # Handle continuous compounding cases
    if compound_type == 'continuous':
        if from_freq == 'continuous':
            # Converting from continuous to discrete
            effective_annual = math.exp(rate) - 1
        else:
            # Converting to continuous from discrete
            if to_freq == 'continuous':
                # First convert to effective annual
                if from_freq == 'annual':
                    effective_annual = rate
                else:
                    effective_annual = (1 + rate/freq_map[from_freq])**freq_map[from_freq] - 1
                # Then convert to continuous
                return math.log(1 + effective_annual)
            else:
                raise ValueError("When compound_type is 'continuous', to_freq must be 'continuous'")
    else:
        # Handle discrete compounding
        if from_freq == 'continuous':
            raise ValueError("For continuous source rate, compound_type must be 'continuous'")
            
        # Convert to effective annual rate first
        if from_freq == 'annual':
            effective_annual = rate
        else:
            # Adjust rate based on day count convention for non-annual frequencies
            if from_freq == 'daily':
                adj_rate = rate * day_count_map[day_count] / 365.25
                effective_annual = (1 + adj_rate/freq_map[from_freq])**freq_map[from_freq] - 1
            else:
                effective_annual = (1 + rate/freq_map[from_freq])**freq_map[from_freq] - 1
        
    # Convert from effective annual to target frequency
    if to_freq == 'continuous':
        return math.log(1 + effective_annual)
    elif to_freq == 'daily':
        # Adjust for day count convention
        unadj_rate = (1 + effective_annual)**(1/freq_map[to_freq]) - 1
        return unadj_rate * 365.25 / day_count_map[day_count]
    else:
        return (1 + effective_annual)**(1/freq_map[to_freq]) - 1

def get_day_count_factor(start_date, end_date, convention='actual/360'):
    """Calculate day count factor based on convention"""
    actual_days = (end_date - start_date).days
    if convention == '30/360':
        return 360  # Simplified 30/360 for now
    return actual_days

class BondCalculator:
    """Enhanced bond calculations including duration and convexity"""
    def __init__(self, face_value, coupon_rate, maturity, settlement_date=None,
                 frequency=2, day_count='30/360'):
        """
        Args:
            face_value: Bond's par value
            coupon_rate: Annual coupon rate as decimal
            maturity: Years to maturity
            settlement_date: Settlement date for accrued interest
            frequency: Payment frequency (2 for semiannual, 12 for monthly)
            day_count: Day count convention for accrued interest
        """
        self.face_value = face_value
        self.coupon_rate = coupon_rate
        self.maturity = maturity
        self.frequency = frequency
        self.day_count = day_count
        self.settlement_date = settlement_date
        
        # Calculate coupon payment
        self.coupon_payment = (face_value * coupon_rate) / frequency
        
    def price(self, ytm):
        """Calculate clean price (excluding accrued interest)
        
        Args:
            ytm: Yield to maturity (annual rate as decimal)
        """
        periods = self.maturity * self.frequency
        rate_per_period = ytm / self.frequency
        
        # Calculate present value of cash flows
        pv_face = self.face_value / (1 + rate_per_period)**periods
        pv_coupons = 0
        
        for t in range(1, int(periods) + 1):
            pv_coupons += self.coupon_payment / (1 + rate_per_period)**t
            
        return pv_face + pv_coupons
        
    def duration(self, ytm):
        """Calculate Macaulay duration
        
        Args:
            ytm: Yield to maturity (annual rate as decimal)
        """
        periods = self.maturity * self.frequency
        rate_per_period = ytm / self.frequency
        price = self.price(ytm)
        
        # Calculate weighted present values
        duration = 0
        for t in range(1, int(periods) + 1):
            # Weight each cash flow by its time period
            if t == periods:
                cf = self.coupon_payment + self.face_value
            else:
                cf = self.coupon_payment
                
            pv_cf = cf / (1 + rate_per_period)**t
            duration += (t * pv_cf)
            
        # Convert to years and normalize by price
        return duration / price / self.frequency
        
    def modified_duration(self, ytm):
        """Calculate modified duration
        
        Args:
            ytm: Yield to maturity (annual rate as decimal)
        """
        mac_duration = self.duration(ytm)
        return mac_duration / (1 + ytm/self.frequency)
        
    def convexity(self, ytm):
        """Calculate convexity
        
        Args:
            ytm: Yield to maturity (annual rate as decimal)
        """
        periods = self.maturity * self.frequency
        rate_per_period = ytm / self.frequency
        price = self.price(ytm)
        
        convexity = 0
        for t in range(1, int(periods) + 1):
            if t == periods:
                cf = self.coupon_payment + self.face_value
            else:
                cf = self.coupon_payment
                
            # Weight by time squared
            pv_cf = cf / (1 + rate_per_period)**t
            convexity += (t * (t + 1) * pv_cf)
            
        # Normalize and adjust for payment frequency
        return convexity / (price * (1 + rate_per_period)**2 * self.frequency**2)
        
    def accrued_interest(self):
        """Calculate accrued interest if settlement date is provided"""
        if not self.settlement_date:
            return 0
            
        # Get the last coupon date and next coupon date
        days_between_coupons = 360 / self.frequency  # Using 360-day year
        days_in_year = 360 if self.day_count == '30/360' else 365
        
        # Calculate days since last coupon
        if self.day_count == '30/360':
            # 30/360 convention
            month_diff = self.settlement_date.month - self.settlement_date.replace(day=1).month
            day_diff = min(30, self.settlement_date.day)
            days_accrued = month_diff * 30 + day_diff
        else:
            # Actual/360 or Actual/365
            last_coupon = self.settlement_date.replace(
                day=1,  # Start of month
                month=((self.settlement_date.month - 1) // (12 // self.frequency)) * (12 // self.frequency) + 1
            )
            days_accrued = (self.settlement_date - last_coupon).days
        
        # Calculate accrued interest
        annual_coupon = self.coupon_rate * self.face_value
        period_coupon = annual_coupon / self.frequency
        
        if self.day_count == '30/360':
            accrued = period_coupon * (days_accrued / days_between_coupons)
        else:
            accrued = period_coupon * (days_accrued / days_in_year) * (self.frequency)
            
        return round_currency(accrued)

class BalanceSheetCalculator:
    """Calculator for balance sheet problems"""
    def __init__(self, items):
        self.items = items  # Dictionary of balance sheet items
        
    def calculate_current_assets(self):
        """Calculate total current assets"""
        return sum([
            self.items.get('cash', 0),
            self.items.get('accounts_receivable', 0),
            self.items.get('inventory', 0)
        ])
        
    def calculate_current_liabilities(self):
        """Calculate total current liabilities"""
        return sum([
            self.items.get('accounts_payable', 0),
            self.items.get('notes_payable', 0)
        ])
        
    def calculate_total_assets(self):
        """Calculate total assets"""
        return self.calculate_current_assets() + self.items.get('net_fixed_assets', 0)
        
    def calculate_total_liabilities(self):
        """Calculate total liabilities"""
        return (self.calculate_current_liabilities() + 
                self.items.get('long_term_debt', 0))
                
    def calculate_retained_earnings(self):
        """Calculate retained earnings as plug number"""
        return (self.calculate_total_assets() - 
                (self.calculate_total_liabilities() + 
                 self.items.get('common_stock', 0)))
                 
    def calculate_nwc(self):
        """Calculate Net Working Capital"""
        return self.calculate_current_assets() - self.calculate_current_liabilities()
        
    def calculate_de_ratio(self):
        """Calculate Debt to Equity ratio"""
        total_equity = (self.items.get('common_stock', 0) + 
                       self.calculate_retained_earnings())
        return self.calculate_total_liabilities() / total_equity if total_equity != 0 else float('inf')
        
    def calculate_all_metrics(self):
        """Calculate all balance sheet metrics"""
        retained_earnings = self.calculate_retained_earnings()
        total_assets = self.calculate_total_assets()
        total_liabilities = self.calculate_total_liabilities()
        
        return {
            'current_assets': {
                'cash': self.items.get('cash', 0),
                'accounts_receivable': self.items.get('accounts_receivable', 0),
                'inventory': self.items.get('inventory', 0),
                'total': self.calculate_current_assets()
            },
            'fixed_assets': {
                'net_fixed_assets': self.items.get('net_fixed_assets', 0),
                'total': self.items.get('net_fixed_assets', 0)
            },
            'total_assets': total_assets,
            'current_liabilities': {
                'accounts_payable': self.items.get('accounts_payable', 0),
                'notes_payable': self.items.get('notes_payable', 0),
                'total': self.calculate_current_liabilities()
            },
            'long_term_liabilities': {
                'long_term_debt': self.items.get('long_term_debt', 0),
                'total': self.items.get('long_term_debt', 0)
            },
            'total_liabilities': total_liabilities,
            'equity': {
                'common_stock': self.items.get('common_stock', 0),
                'retained_earnings': retained_earnings,
                'total': self.items.get('common_stock', 0) + retained_earnings
            },
            'key_metrics': {
                'nwc': self.calculate_nwc(),
                'de_ratio': self.calculate_de_ratio()
            }
        }

def analyze_with_gemini(problem_text):
    """Use Gemini to analyze financial problem text"""
    
    # Basic instructions without any variable interpolation
    basic_instructions = """You are a financial calculator that extracts parameters from word problems. First, determine if this is a Time Value of Money (TVM) problem or a Balance Sheet problem.

For Balance Sheet problems:
1. Look for keywords: 
   - "balance sheet"
   - "retained earnings"
   - "working capital"
   - Lists of assets and liabilities

2. Extract all balance sheet items and convert to numbers:
   - Remove $ signs and commas
   - Convert to float values
   - Handle "and" or "&" in item names
   - Standardize names (e.g., "PPE" to "net_fixed_assets")

3. Categorize items:
   Current Assets:
   - cash
   - accounts_receivable
   - inventory

   Fixed Assets:
   - net_fixed_assets (also called PPE)

   Current Liabilities:
   - accounts_payable (including accruals)
   - notes_payable

   Long-term Liabilities:
   - long_term_debt

   Equity:
   - common_stock (including paid-in capital)

4. Return in format:
   {
     "problem_type": "BALANCE_SHEET",
     "items": {
       "cash": 134000.00,
       "accounts_receivable": 105000.00,
       "inventory": 293000.00,
       "net_fixed_assets": 1730000.00,
       "accounts_payable": 210000.00,
       "notes_payable": 160000.00,
       "long_term_debt": 845000.00,
       "common_stock": 500000.00
     }
   }

For TVM problems:
1. Look for keywords:
   - Interest rates
   - Time periods
   - Payment amounts
   - Present/future values

2. Identify if this is a comparison problem:
   - Look for: "which option", "compare", "choose between", "or"
   - Check for different payment structures
   - Check for different rates or terms

3. Set comparison_type if needed:
   - "payment_structure" for comparing lump sum vs payments
   - "rate" for comparing different interest rates"""
    
    # Multi-step calculation examples using raw strings to avoid f-string issues
    multi_step_examples = r"""
For multi-step calculations:
1. Multiple Account Problems:
    - Calculate each account separately first
    - Use clear id names: "stock_fv", "bond_fv"
    - Use combined value in final step: "pv": "{stock_fv}+{bond_fv}"
    Example: "$1100/month in stocks (8%) and $500/month in bonds (4%)"
    → Step 1: FV of stock account
    → Step 2: FV of bond account
    → Step 3: Combine for total value

2. Two-Phase Problems:
    - First calculate accumulation phase
    - Use result as input for distribution phase
    - Keep rates separate for each phase
    Example: "Save for 15 years, then withdraw for 20 years"
    → Step 1: FV after savings period
    → Step 2: PMT using FV as starting point

3. Bond Calculations:
    Example: "7% coupon bond, $1000 face value, pays semiannually, 16 years remaining, YTM 6.48%. Calculate bond price."
    {
      "steps": [
        {
          "id": "bond_price",
          "problem_type": "PV",
          "result_var": "bond_price",
          "params": {
            "rate": 0.0324,  # YTM divided by 2 for semiannual
            "nper": 32,      # Years * 2 for semiannual
            "pmt": 35,
            "fv": 1000,
            "payment_frequency": "semiannual",
            "is_bond": true
          },
          "final_step": true
        }
      ]
    }"""

    # Credit card comparison example as a separate raw string
    comparison_examples = r"""4. Rate Comparison Problems:
    - Calculate NPER or PMT for each rate
    - Use arithmetic to find difference
    Example: "Compare 19.2% vs 9.2% credit card payments"
    Steps:
    {
      "steps": [
        {
          "id": "old_card",
          "problem_type": "NPER",
          "result_var": "old_payments",
          "params": {
            "rate": 0.192,
            "pmt": -250,
            "pv": 5000,
            "payment_frequency": "monthly"
          }
        },
        {
          "id": "new_card",
          "problem_type": "NPER",
          "result_var": "new_payments",
          "params": {
            "rate": 0.092,
            "pmt": -250,
            "pv": 5000,
            "payment_frequency": "monthly"
          },
          "final_step": true
        }
      ],
      "comparison_type": "rate"
    }
    
    5. Payment Structure Comparison Problems:
    - Compare different payment structures (e.g., lump sum vs payments)
    - Calculate present value for payment stream
    - Compare with lump sum option
    Example: "Choose between $200,000 lump sum or $1,400 monthly for 20 years at 6%"
    Steps:
    {
      "steps": [
        {
          "id": "monthly_payments",
          "problem_type": "PV",
          "result_var": "payment_stream_pv",
          "params": {
            "rate": 0.06,
            "nper": 20,
            "pmt": -1400,
            "fv": 0,
            "payment_frequency": "monthly"
          }
        },
        {
          "id": "lump_sum",
          "problem_type": "PV",
          "result_var": "lump_sum_pv",
          "params": {
            "pv": 200000
          }
        },
        {
          "id": "comparison",
          "problem_type": "COMPARE",
          "params": {
            "option1": "{lump_sum_pv}",
            "option2": "{payment_stream_pv}",
            "comparison_type": "'payment_structure'"
          },
          "result_var": "better_option",
          "final_step": true
        }
      ],
      "comparison_type": "payment_structure"
    }"""

    # Additional calculation types and rules
    additional_rules = r"""5. Real Rate Problems:
    - When inflation mentioned, adjust rate
    - Real rate = (1 + nominal)/(1 + inflation) - 1
    Example: "11% return with 3.2% inflation"
    {
      "steps": [
        {
          "id": "real_rate",
          "problem_type": "RATE",
          "result_var": "real_rate",
          "params": {
            "nominal_rate": 0.11,
            "inflation_rate": 0.032
          },
          "final_step": true
        }
      ]
    }

6. Timing Rules:
    - Set payment_frequency based on payment schedule:
      * Monthly payments: payment_frequency = 'monthly'
      * Semiannual payments: payment_frequency = 'semiannual'
      * Annual payments: payment_frequency = 'annual'
    - End of period: no adjustment needed
    - Beginning of period: when=1 in calculation

7. Sign Conventions:
    - Payments made: negative
    - Investments made: negative
    - Future values received: positive
    - Present values received: positive

8. Result Variable Rules:
    - Use descriptive names: "retirement_savings", "loan_payment"
    - Include type in name: "stock_fv", "bond_pv"
    - Reference with exact syntax: "{result_var}"
    - Combine values in parameter: "pv": "{var1}+{var2}", "fv": "{var1}-{var2}"

9. Step Dependencies:
    - List all required prior steps in depends_on
    - Order steps to resolve dependencies
    - Only mark final_step: true on last step
    - Include all needed params in each step
    - Validate all referenced variables exist"""

    # Parameter extraction instructions
    param_instructions = """
2. Extract these parameters if mentioned:
    - rate: Convert percentage to decimal (e.g., 8% → 0.08)
    - nper: Number of time periods (in years)
    - pmt: Payment amount (negative for payments made)
    - pv: Present value (negative for investments made)
    - fv: Future value
    - payment_frequency: 'annual', 'semiannual', or 'monthly'
    - inflation_rate: If mentioned, used to calculate real rate
    - is_bond: true for bond calculations with semiannual payments
    - compound_type: 'discrete' or 'continuous' if mentioned
    Look for keywords: 'continuous', 'continuously compounded', 'day count', 'settlement date'"""

    # JSON template as a raw string
    json_template = r"""
3. Return a JSON object with only the relevant parameters:
{
     "steps": [
         {
             "id": "step1",
             "problem_type": "FV|PV|PMT|NPER|RATE",
             "depends_on": [],
             "result_var": "result1",
             "params": {
                 "rate": 0.00,
                 "nper": 0,
                 "pmt": 0,
                 "pv": 0,
                 "fv": 0,
                 "payment_frequency": "annual",
                 "inflation_rate": null,
                  "compound_type": "discrete",
                 "is_bond": false
             },
             "final_step": false
         }
     ]
}"""

    # Important notes
    important_notes = """
Important:
    - Only include parameters that are explicitly mentioned or can be clearly inferred
    - Convert all percentages to decimals
    - Make payments and investments negative values
    - Return only valid JSON, no other text or markdown"""

    # Combine all parts of the prompt
    full_instructions = "\n".join([
        basic_instructions,
        multi_step_examples,
        comparison_examples,
        additional_rules,
        param_instructions,
        json_template,
        important_notes
    ])
    
    # Create the final prompt with the problem text
    prompt = f"Problem: {problem_text}\n\n{full_instructions}"

    try:
        response = model.generate_content(
            prompt,
            safety_settings=[{"category": "HARM_CATEGORY_DANGEROUS", "threshold": "BLOCK_NONE"}],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                candidate_count=1,
                top_p=0.1,
                max_output_tokens=2048,
                top_k=1,
            )
        )

        # Log the full prompt for debugging
        sys.stderr.write(f"Full Gemini prompt:\n{prompt}\n")
        
        # Get just the response text
        json_str = response.text.strip()

        # Log the raw response for debugging
        sys.stderr.write(f"Raw Gemini response:\n{json_str}\n")
        
        # Clean up the response
        if '```json' in json_str:
            json_str = json_str.split('```json')[1].split('```')[0].strip()
        elif '```' in json_str:
            json_str = json_str.split('```')[1].split('```')[0].strip()
        
        result = json.loads(json_str)
        return result
    except Exception as e:
        sys.stderr.write(f"Gemini Error Type: {type(e).__name__}\n")
        sys.stderr.write(f"Gemini Error Details: {str(e)}\n")
        return None

def calculate_financial(problem_type, params):
    """Calculate financial result using numpy-financial"""
    try:        
        # Extract and validate parameters
        rate = params.get('rate', 0)
        nper = params.get('nper', 0)
        pmt = params.get('pmt', 0)
        pv = params.get('pv', 0)
        fv = params.get('fv', 0)
        payment_freq = params.get('payment_frequency', 'annual')
        inflation_rate = params.get('inflation_rate')
        is_bond = params.get('is_bond', False)
        compound_type = params.get('compound_type', 'discrete')
        
        # Validate payment frequency
        valid_frequencies = ['annual', 'semiannual', 'monthly']
        if payment_freq not in valid_frequencies:
            raise ValueError(f"Invalid payment frequency: {payment_freq}. Must be one of {valid_frequencies}")

        # Handle legacy monthly_payments flag
        if params.get('monthly_payments', False):
            sys.stderr.write("Warning: monthly_payments flag is deprecated. Use payment_frequency='monthly' instead.\n")
            payment_freq = 'monthly'

        # Calculate real rate if inflation rate is provided
        if inflation_rate is not None:
            if problem_type == 'RATE':
                # For RATE problems, just calculate real rate directly
                return calculate_real_rate(params['nominal_rate'], inflation_rate)
            else:
                # For other problems, adjust the rate
                rate = calculate_real_rate(rate, inflation_rate)

        # Handle continuous compounding
        if compound_type == 'continuous':
            if payment_freq != 'continuous':
                # Convert continuous rate to discrete rate for the given frequency
                rate = convert_rate(rate, 'continuous', payment_freq)
            else:
                # Use continuous rate directly
                return math.exp(rate * nper) * pv if problem_type == 'FV' else pv * math.exp(-rate * nper)

        # Handle discrete compounding
        if payment_freq == 'monthly':
            rate = rate / 12  # For monthly payments, simply divide by 12
            nper = nper * 12
        elif payment_freq == 'semiannual':
            if not is_bond:  # For non-bond calculations, convert the rate
                rate = convert_rate(rate, 'annual', 'semiannual')  # For bonds, rate is already adjusted
            if is_bond:
                nper = nper  # For bonds, nper is already in semiannual periods
            else:
                nper = math.ceil(nper * 2)  # Round up for fractional years in non-bond calculations
        
        # Special case: when only PV is provided, just return it
        if problem_type == 'PV' and pv != 0 and not any([rate, nper, pmt, fv]):
            return pv
        
        # Standard financial calculations with numpy-financial
        calculators = {
            'FV': lambda: npf.fv(rate, nper, pmt, pv),
            'PV': lambda: npf.pv(rate, nper, pmt, fv),
            'PMT': lambda: npf.pmt(rate, nper, pv, fv),
            'NPER': lambda: npf.nper(rate, pmt, pv, fv),
            'RATE': lambda: npf.rate(nper, pmt, pv, fv),
            'COMPARE': lambda: {
                'payment_structure': lambda: float(params['option1']) > float(params['option2']), 
                'rate': lambda: float(params['option1']) < float(params['option2'])
            }[params.get('comparison_type', 'payment_structure').replace("'", "")]()
        }
        
        calculator = calculators.get(problem_type)
        if not calculator:
            raise ValueError(f"Unknown problem type: {problem_type}")
            
        result = calculator()
        # Convert numpy types to Python float
        if hasattr(result, 'item'):
            result = result.item()

        # Special handling for bond PV calculations
        if problem_type == 'PV' and is_bond:
            # Bond prices are quoted as positive values
            result = -result
            
            # For bonds with continuous compounding
            if compound_type == 'continuous':
                # Adjust for continuous interest accrual
                result = result * math.exp(rate * (nper % 1))
            
        # Special handling for RATE calculations
        if problem_type == 'RATE' and payment_freq != 'annual':
            # Convert back to annual rate
            result = convert_rate(result, payment_freq, 'annual')
            
        return result
        
    except Exception as e:
        raise e

def evaluate_expression(expr, results):
    """Evaluate an expression containing result variables"""
    if not isinstance(expr, str):
        return expr
        
    # Don't evaluate payment frequency and other string parameters
    if expr in ['annual', 'semiannual', 'monthly', 'payment_structure', 'rate'] or (expr.startswith("'") and expr.endswith("'")):
        return expr
        
    # Find all variable references in the expression
    var_pattern = re.compile(r'\{([^}]+)\}')
    
    try:
        # Simple variable reference
        if var_pattern.match(expr) and len(expr) == var_pattern.match(expr).end():
            var_name = var_pattern.match(expr).group(1)
            if var_name not in results:
                raise ValueError(f"Missing dependency: {var_name}")
            return float(results[var_name])
        
        # Replace all variable references with their values
        evaluated_expr = var_pattern.sub(lambda m: str(float(results[m.group(1)])), expr)
        return float(eval(evaluated_expr))
    except Exception as e:
        raise ValueError(f"Failed to evaluate expression '{expr}': {str(e)}\nAvailable variables: {list(results.keys())}")
    return expr

def solve_financial_problem(args):
    """Solve financial problem"""
    try:
        sys.stderr.write(f"Solving problem with args: {json.dumps(args, indent=2)}\n")
        # Handle balance sheet problems
        if 'problem_type' in args and args['problem_type'] == 'BALANCE_SHEET':
            calculator = BalanceSheetCalculator(args.get('items', {}))
            return {
                'success': True,
                'problem_type': 'BALANCE_SHEET',
                'results': calculator.calculate_all_metrics()
            }

        steps = args.get('steps', [])
        if not steps:
            # Handle legacy single-step format
            steps = [{
                'id': 'single',
                'problem_type': args['problem_type'],
                'params': args['params'],
                'final_step': True
            }]
        
        results = {}
        final_result = None
        
        # Process steps in order
        for step in steps:
            # Resolve any dependencies
            params = step['params'].copy()
            sys.stderr.write(f"Processing step: {json.dumps(step, indent=2)}\n")
            
            # Evaluate any arithmetic expressions in parameters
            for param, value in params.items():
                try:
                    if param == 'comparison_type':
                        # Handle comparison_type directly
                        evaluated_value = value.replace("'", "")
                    else:
                        evaluated_value = evaluate_expression(value, results)
                    params[param] = evaluated_value
                except Exception as e:
                    raise ValueError(f"Failed to evaluate {param}: {str(e)}")
            
            # Calculate this step
            result = calculate_financial(step['problem_type'], params)
            
            # Handle bond calculations if needed
            if step.get('params', {}).get('is_bond', False):
                try:
                    # Create bond calculator
                    bond = BondCalculator(
                        face_value=params['fv'],
                        coupon_rate=params['rate'] * 2,  # Convert to annual rate
                        maturity=params['nper'] / 2,  # Convert to years
                        frequency=2  # Semiannual payments
                    )
                    
                    # Calculate bond metrics
                    ytm = params['rate'] * 2  # Convert to annual rate
                    duration = bond.duration(ytm)
                    modified_duration = bond.modified_duration(ytm)
                    convexity = bond.convexity(ytm)
                    
                    # Add metrics to results
                    results[f"{step['result_var']}_duration"] = duration
                    results[f"{step['result_var']}_modified_duration"] = modified_duration
                    results[f"{step['result_var']}_convexity"] = convexity
                    
                    # If this is the final step, include metrics in final result
                    if step.get('final_step', False):
                        final_result = {
                            'price': result,
                            'duration': duration,
                            'modified_duration': modified_duration,
                            'convexity': convexity
                        }
                        result = final_result
                except Exception as e:
                    sys.stderr.write(f"Warning: Bond metrics calculation failed: {str(e)}\n")
            
            results[step['result_var']] = result
            if step.get('final_step', False):
                final_result = result

        # Only round currency values, not metrics
        if isinstance(final_result, (int, float)):
            final_result = round_currency(final_result)
            
        return {
            'success': True,
            'result': final_result,
            'intermediate_results': results,
            'steps_executed': len(steps)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def analyze_financial_problem(args):
    """Analyze financial problem text and extract parameters"""
    try:
        problem_text = args['problem_text']
        
        # Use Gemini to analyze the problem
        gemini_result = analyze_with_gemini(problem_text)
        
        if not gemini_result:
            return {
                'success': False,
                'error': 'Failed to analyze problem with Gemini'
            }

        # Handle balance sheet problems
        if gemini_result.get('problem_type') == 'BALANCE_SHEET':
            return {
                'success': True,
                'problem_type': 'BALANCE_SHEET',
                'items': gemini_result.get('items', {})
            }

        # Handle TVM problems
        if 'steps' in gemini_result:
            # Handle both single-step and multi-step results
            return {
                'success': True,
                'steps': gemini_result['steps'],
                    'comparison_type': gemini_result.get('comparison_type')
                }
            return {
                'success': True,
                'steps': [{'problem_type': gemini_result['problem_type'], 'params': gemini_result['params'], 'final_step': True}]
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def main():
    if len(sys.argv) != 3:
        json.dump({
            'success': False,
            'error': 'Invalid number of arguments'
        }, sys.stdout)
        sys.exit(1)
        
    command = sys.argv[1]
    try:
        args = json.loads(sys.argv[2])
    except json.JSONDecodeError:
        json.dump({
            'success': False,
            'error': 'Invalid JSON arguments'
        }, sys.stdout)
        sys.exit(1)
        
    # Command router
    command_map = {
        'solve_financial_problem': solve_financial_problem,
        'analyze_financial_problem': analyze_financial_problem
    }
    
    if command not in command_map:
        json.dump({
            'success': False,
            'error': f'Unknown command: {command}'
        }, sys.stdout)
        sys.exit(1)
        
    result = command_map[command](args)
    json.dump(result, sys.stdout)

if __name__ == '__main__':
    main()
