#!/usr/bin/env python3
import json
import sys
import os
import google.generativeai as genai
from financial_operations import analyze_financial_problem, solve_financial_problem

# Configure Gemini
genai.configure(api_key='AIzaSyAeSZswx2CCRmLk4b5rCu-aH0qIBsH1zn4')
model = genai.GenerativeModel('gemini-2.0-flash-001')

# Configure paths
INSTRUCTIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'excel_instructions')

def ensure_instructions_dir():
    """Ensure the instructions directory exists"""
    if not os.path.exists(INSTRUCTIONS_DIR):
        os.makedirs(INSTRUCTIONS_DIR)
    # Reset question tracker when directory is created
    tracker_file = os.path.join(INSTRUCTIONS_DIR, 'question_tracker.json')
    if not os.path.exists(tracker_file):
        with open(tracker_file, 'w') as f:
            json.dump({'current_number': 0}, f)

def get_instruction_filepath(question_number):
    """Generate filepath for instruction file"""
    return os.path.join(INSTRUCTIONS_DIR, f'question_{question_number}_instructions.txt')

def format_currency(amount):
    """Format number as currency string"""
    return f"${amount:,.2f}"

def generate_balance_sheet_instructions(results):
    """Generate instructions for balance sheet problems"""
    # Extract values from results
    current_assets = results['current_assets']
    fixed_assets = results['fixed_assets']
    current_liab = results['current_liabilities']
    long_term_liab = results['long_term_liabilities']
    equity = results['equity']
    metrics = results['key_metrics']
    
    instructions = f"""
Balance Sheet Structure and Calculations:

1. Assets
   A. Current Assets:
      - Cash: {format_currency(current_assets['cash'])}
      - Accounts Receivable: {format_currency(current_assets['accounts_receivable'])}
      - Inventory: {format_currency(current_assets['inventory'])}
      Total Current Assets: {format_currency(current_assets['total'])}

   B. Fixed Assets:
      - Net Fixed Assets (PPE): {format_currency(fixed_assets['net_fixed_assets'])}
      Total Fixed Assets: {format_currency(fixed_assets['total'])}

   Total Assets: {format_currency(results['total_assets'])}

2. Liabilities & Stockholders' Equity
   A. Current Liabilities:
      - Accounts Payable: {format_currency(current_liab['accounts_payable'])}
      - Notes Payable: {format_currency(current_liab['notes_payable'])}
      Total Current Liabilities: {format_currency(current_liab['total'])}

   B. Long-term Liabilities:
      - Long-term Debt: {format_currency(long_term_liab['long_term_debt'])}
      Total Long-term Liabilities: {format_currency(long_term_liab['total'])}

   C. Stockholders' Equity:
      - Common Stock: {format_currency(equity['common_stock'])}
      - Retained Earnings: {format_currency(equity['retained_earnings'])}
      Total Stockholders' Equity: {format_currency(equity['total'])}

   Total Liabilities & Equity: {format_currency(results['total_liabilities'] + equity['total'])}

Key Financial Metrics:

1. Net Working Capital (NWC):
   Calculation: Current Assets - Current Liabilities
   {format_currency(current_assets['total'])} - {format_currency(current_liab['total'])} = {format_currency(metrics['nwc'])}

2. Debt to Equity Ratio (D/E):
   Calculation: Total Liabilities / Total Equity
   {format_currency(results['total_liabilities'])} / {format_currency(equity['total'])} = {metrics['de_ratio']:.2f}

Verification:
1. Balance Sheet Balances:
   Total Assets = Total Liabilities + Total Equity
   {format_currency(results['total_assets'])} = {format_currency(results['total_liabilities'] + equity['total'])}

2. Retained Earnings Calculation:
   Total Assets - (Total Liabilities + Common Stock)
   {format_currency(results['total_assets'])} - ({format_currency(results['total_liabilities'])} + {format_currency(equity['common_stock'])})
   = {format_currency(equity['retained_earnings'])}
"""
    return instructions

def generate_excel_instructions(problem_text, question_number):
    """Generate Excel instructions from financial problem analysis and solution"""
    try:
        # Get results directly from financial_operations.py
        analysis_result = analyze_financial_problem({"problem_text": problem_text})
        if not analysis_result.get('success', False):
            raise ValueError(f"Analysis failed: {analysis_result.get('error', 'Unknown error')}")
            
        solve_result = solve_financial_problem(analysis_result)
        if not solve_result.get('success', False):
            raise ValueError(f"Solution failed: {solve_result.get('error', 'Unknown error')}")
            
        # Handle balance sheet problems differently
        if solve_result.get('problem_type') == 'BALANCE_SHEET':
            instructions = generate_balance_sheet_instructions(solve_result['results'])
            return {
                'success': True,
                'instructions': instructions
            }

        # Handle bond problems
        if any(step.get('params', {}).get('is_bond', False) for step in analysis_result.get('steps', [])):
            bond_step = next(step for step in analysis_result['steps'] if step['params'].get('is_bond'))
            bond_template = f"""
For Question #{question_number}, generate Excel instructions for bond valuation:

A. Inputs:
Face_Value = ${bond_step['params']['fv']:,.2f}
Coupon_Rate = {bond_step['params']['rate'] * 2:.2%} (annual)
YTM = {bond_step['params']['rate'] * 2:.2%} (annual)
Years_Remaining = {bond_step['params']['nper'] / 2}
Payment_Frequency = Semiannual

[blank line]
B. Calculations:
1. Semiannual_Rate = Annual YTM / 2
   Excel: ={bond_step['params']['rate'] * 2:.2%}/2
   ► Must equal: {bond_step['params']['rate']:.2%}

2. Number_of_Periods = Years * 2
   Excel: ={bond_step['params']['nper'] / 2}*2
   ► Must equal: {bond_step['params']['nper']}

3. Coupon_Payment = Face Value * (Annual Coupon Rate / 2)
   Excel: =${bond_step['params']['fv']:,.2f}*({bond_step['params']['rate'] * 2:.2%}/2)
   ► Must equal: ${bond_step['params']['pmt']:.2f}

[blank line]
C. Bond Price Calculation:
Bond_Price = PV of coupon payments + PV of face value
Excel: =PV(Semiannual_Rate, Number_of_Periods, -Coupon_Payment, -Face_Value)
► Must equal: ${solve_result['result']:,.2f}

[blank line]
D. Verification:
1. The bond price represents the present value of:
   - {bond_step['params']['nper']} semiannual coupon payments of ${bond_step['params']['pmt']:.2f}
   - Face value of ${bond_step['params']['fv']:,.2f} at maturity

2. Price Components:
   - PV of Coupons: =PV(Semiannual_Rate, Number_of_Periods, -Coupon_Payment)
   - PV of Face Value: =PV(Semiannual_Rate, Number_of_Periods, 0, -Face_Value)

3. Market Rate vs Coupon Rate:
   {f"Bond sells at premium (Price > Face Value)" if solve_result['result'] > bond_step['params']['fv'] else
    f"Bond sells at discount (Price < Face Value)" if solve_result['result'] < bond_step['params']['fv'] else
    f"Bond sells at par (Price = Face Value)"}
"""
            return {'success': True, 'instructions': bond_template}

        # Determine if this is a comparison problem
        is_comparison = analysis_result.get('comparison_type') is not None

        # Base template for all problems
        base_template = f"""
For Question #{question_number}, generate Excel instructions in this exact format:

A. Inputs:
Option_1_Amount = $200,000 (lump sum)
Option_2_Payment = $1,400 (monthly)
Interest_Rate = 6%
Years = 20
Payment_Frequency = Monthly

[blank line]
B. Calculations:
1. MonthlyInterestRate = Interest rate divided by 12
   Excel: =6%/12
   ► Must equal: 0.005

2. NumberOfPayments = Years * 12
   Excel: =20*12
   ► Must equal: 240

3. TotalPayments = Monthly payment * Number of payments
   Excel: =1400*240
   ► Must equal: $336,000

4. PresentValueOfPayments = Present value of monthly payments
   Excel: =PV(MonthlyInterestRate, NumberOfPayments, -Option_2_Payment)
   ► Must equal: $195,413.21

[blank line]
C. Final Calculation:
Decision = Compare lump sum to present value
Note: Choose option with higher present value

Excel with values:    =IF(200000 > 195413.21, "Take lump sum", "Take monthly payments")
Excel with variables: =IF(Option_1_Amount > PresentValueOfPayments, "Take lump sum", "Take monthly payments")
► Must equal: "Take lump sum" (because $200,000 > $195,413.21)"""

        # Additional template for comparison problems
        comparison_template = """

D. Decision Analysis:
1. Option Comparison:
   Excel: =CONCATENATE(
     "Lump Sum ($", TEXT(Option_1_Amount, "#,##0"), "): ",
     IF(Option_1_Amount > PresentValueOfPayments, "Better", "Worse"),
     " than monthly payments worth $", TEXT(PresentValueOfPayments, "#,##0")
   )
   ► Must equal: "Lump Sum ($200,000): Better than monthly payments worth $195,413"

2. Total Payments Analysis:
   Excel: =CONCATENATE(
     "Total payments ($", TEXT(TotalPayments, "#,##0"),
     ") exceed lump sum by $", TEXT(TotalPayments - Option_1_Amount, "#,##0")
   )
   ► Must equal: "Total payments ($336,000) exceed lump sum by $136,000"

3. Time Value Analysis:
   Excel: =CONCATENATE(
     "Monthly payments worth $", TEXT(PresentValueOfPayments, "#,##0"),
     " in today's dollars ($", TEXT(TotalPayments - PresentValueOfPayments, "#,##0"),
     " lost to time value of money)"
   )
   ► Must equal: "Monthly payments worth $195,413 in today's dollars ($140,587 lost to time value of money)"

4. Final Recommendation:
   Take the $200,000 lump sum because:
   - It has a higher present value ($200,000 vs $195,413)
   - Provides immediate access to full amount
   - Avoids loss of $140,587 to time value of money
   - Offers more flexibility for investment or immediate use"""

        # Combine templates based on problem type
        prompt = base_template + (comparison_template if is_comparison else "") + f"""

Important formatting rules:
1. Show percentages as percentages (7% not 0.07)
2. Show currency with $ sign
3. Use descriptive text for frequencies (Monthly not 12)
4. Use consistent variable names:
   - MonthlyInterestRate for the rate per period
   - NumberOfPayments for total periods
   - Option_1_Amount for lump sum
   - Option_2_Payment for periodic payment
5. Explain the decision criteria in the Note
6. Align the final formulas for easy comparison
7. Use arrows (►) to highlight expected values
8. Add blank lines between major sections

Use these calculation results:
Analysis Result:
{json.dumps(analysis_result, indent=2)}

Solution Result:
{json.dumps(solve_result, indent=2)}
"""

        # Generate instructions
        response = model.generate_content(
            prompt,
            safety_settings=[{"category": "HARM_CATEGORY_DANGEROUS", "threshold": "BLOCK_NONE"}],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                candidate_count=1,
                top_p=0.1,
                max_output_tokens=2048,
                top_k=1
            )
        )

        return {
            'success': True,
            'instructions': response.text
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def write_instructions_to_file(instructions, question_number):
    """Write the generated instructions to a numbered file"""
    try:
        # Ensure directory exists
        ensure_instructions_dir()
        
        # Get filepath for this question
        filepath = get_instruction_filepath(question_number)
        
        # Write instructions with header
        with open(filepath, 'w') as f:
            f.write(f"Excel Instructions for Question #{question_number}\n")
            f.write("=" * 50 + "\n\n")
            f.write(instructions)
            
        return {
            'success': True,
            'file': filepath
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
            'error': 'Usage: excel_instructions_generator.py <problem_text> <question_number>'
        }, sys.stdout)
        sys.exit(1)

    problem_text = sys.argv[1]
    try:
        question_number = int(sys.argv[2])
    except ValueError:
        json.dump({
            'success': False,
            'error': 'Question number must be an integer'
        }, sys.stdout)
        sys.exit(1)

    # Generate instructions
    result = generate_excel_instructions(problem_text, question_number)
    if not result['success']:
        json.dump(result, sys.stdout)
        sys.exit(1)

    # Write to numbered file
    write_result = write_instructions_to_file(result['instructions'], question_number)
    json.dump(write_result, sys.stdout)

if __name__ == '__main__':
    main()