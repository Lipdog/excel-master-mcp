
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
    return float(Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def calculate_real_rate(nominal_rate, inflation_rate):
    """Calculate real rate using Fisher Effect: (1 + R) = (1 + r)(1 + h)"""
    return (1 + nominal_rate) / (1 + inflation_rate) - 1

def convert_rate(rate, from_freq, to_freq):
    """Convert interest rate between different payment frequencies"""
    freq_map = {
        'annual': 1,
        'semiannual': 2,
        'monthly': 12
    }
    
    if from_freq not in freq_map or to_freq not in freq_map:
        raise ValueError(f"Invalid frequency. Must be one of: {list(freq_map.keys())}")
        
    if from_freq == to_freq:
        return rate
        
    # Convert to effective annual rate then to target frequency
    effective_annual = (1 + rate/freq_map[from_freq])**freq_map[from_freq] - 1
    return (1 + effective_annual)**(1/freq_map[to_freq]) - 1

def analyze_with_gemini(problem_text):
    """Use Gemini to analyze financial problem text"""
    
    # Basic instructions without any variable interpolation
    basic_instructions = """You are a financial calculator that extracts parameters from word problems.

Instructions:
1. Identify the type of financial calculation needed:
    - FV (Future Value): Finding final amount after investment/growth
    - PV (Present Value): Finding initial amount needed for future goal
    - PMT (Payment): Finding periodic payment amount
    - NPER (Number of Periods): Finding time needed in years
    - RATE (Interest Rate): Finding required interest rate"""
    
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
    credit_card_example = r"""4. Rate Comparison Problems:
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
      ]
    }"""

    # Additional calculation types and rules
    additional_rules = r"""5. Real Rate Problems:
    - When inflation mentioned, adjust rate
    - Real rate = (1 + nominal)/(1 + inflation) - 1
    Example: "11% return with 3.2% inflation"
    → Set inflation_rate: 0.032

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
    - is_bond: true for bond calculations with semiannual payments"""

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
        credit_card_example,
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
        # Extract parameters with validation
        rate = params.get('rate', 0)
        nper = params.get('nper', 0)
        pmt = params.get('pmt', 0)
        pv = params.get('pv', 0)
        fv = params.get('fv', 0)
        payment_freq = params.get('payment_frequency', 'annual')
        inflation_rate = params.get('inflation_rate')
        is_bond = params.get('is_bond', False)
        
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
            rate = calculate_real_rate(rate, inflation_rate)

        # Convert rate and adjust periods based on payment frequency
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
        
        calculators = {
            'FV': lambda: npf.fv(rate, nper, pmt, pv),
            'PV': lambda: npf.pv(rate, nper, pmt, fv),
            'PMT': lambda: npf.pmt(rate, nper, pv, fv),
            'NPER': lambda: npf.nper(rate, pmt, pv, fv),
            'RATE': lambda: npf.rate(nper, pmt, pv, fv)
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
    if expr in ['annual', 'semiannual', 'monthly']:
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
            
            # Evaluate any arithmetic expressions in parameters
            for param, value in params.items():
                try:
                    evaluated_value = evaluate_expression(value, results)
                    params[param] = evaluated_value
                except Exception as e:
                    raise ValueError(f"Failed to evaluate {param}: {str(e)}")
            
            # Calculate this step
            result = calculate_financial(step['problem_type'], params)
            
            results[step['result_var']] = result
            if step.get('final_step', False):
                final_result = result

        # Only round the final result
        if final_result is not None:
            final_result = round_currency(final_result)
            # Update the rounded final result in results dict
            results[step['result_var']] = final_result
            
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
        
        if gemini_result:
            # Handle both single-step and multi-step results
            if 'steps' in gemini_result:
                return {
                    'success': True,
                    'steps': gemini_result['steps']
                }
            return {
                'success': True,
                'steps': [{'problem_type': gemini_result['problem_type'], 'params': gemini_result['params'], 'final_step': True}]
            }
            
        # If Gemini fails, return error
        return {
            'success': False,
            'error': 'Failed to analyze problem with Gemini'
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
