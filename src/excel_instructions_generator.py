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

        # Create prompt for Gemini
        prompt = f"""
For Question #{question_number}, generate Excel instructions in this exact format:

A. Inputs:
Face_Value = $1000
Coupon_Rate = 7%
Years_to_Maturity = 16
Yield_to_Maturity = 6.48%
Payment_Frequency = Semiannual

[blank line]
B. Calculations:
1. SemiannualYTM = Yield to maturity divided by 2
   Excel: =6.48%/2
   ► Must equal: 0.0324

2. Periods = Years to maturity multiplied by 2
   Excel: =16*2
   ► Must equal: 32

3. SemiannualPayment = (Coupon rate * Face value) / 2
   Excel: =(7%*1000)/2
   ► Must equal: 35

[blank line]
C. Final Calculation:
BondPrice = Present Value of Bond
Note: Negative signs on payment and face value represent cash outflows in PV function

Excel with values:    =PV(0.0324, 32, -35, -1000)
Excel with variables: =PV(SemiannualYTM, Periods, -SemiannualPayment, -FaceValue)
► Must equal: 1051.32

Important formatting rules:
1. Show percentages as percentages (7% not 0.07)
2. Show currency with $ sign
3. Use descriptive text for frequencies (Semiannual not 2)
4. Use consistent variable names:
   - SemiannualYTM for the rate per period
   - Periods for number of periods
   - SemiannualPayment for the payment amount
   - FaceValue for the principal
5. Explain negative signs in the Note
6. Align the final formulas for easy comparison
7. Use arrows (►) to highlight expected values
8. Add blank lines between major sections (A, B, C)

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