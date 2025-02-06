#!/usr/bin/env python3
import json
import sys
import os
from financial_operations import analyze_financial_problem, solve_financial_problem
from excel_instructions_generator import generate_excel_instructions, write_instructions_to_file

class QuestionTracker:
    """Track question numbers across sessions"""
    def __init__(self):
        self.tracker_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'excel_instructions',
            'question_tracker.json'
        )
        self.current_number = self._load_current_number()
    
    def _load_current_number(self):
        """Load the current question number from file"""
        try:
            if os.path.exists(self.tracker_file):
                with open(self.tracker_file, 'r') as f:
                    data = json.load(f)
                    return data.get('current_number', 0)
        except Exception as e:
            sys.stderr.write(f"Error loading question number: {str(e)}\n")
        return 0
    
    def _save_current_number(self):
        """Save the current question number to file"""
        try:
            os.makedirs(os.path.dirname(self.tracker_file), exist_ok=True)
            with open(self.tracker_file, 'w') as f:
                json.dump({'current_number': self.current_number}, f)
        except Exception as e:
            sys.stderr.write(f"Error saving question number: {str(e)}\n")
    
    def get_next_number(self):
        """Get the next question number and save it"""
        self.current_number += 1
        self._save_current_number()
        return self.current_number

def process_financial_problem(args):
    """Process a financial problem through all steps"""
    try:
        # Validate input
        if 'problem_text' not in args:
            return {
                'success': False,
                'error': 'problem_text is required'
            }
        
        problem_text = args['problem_text']
        sys.stderr.write(f"Processing problem: {problem_text}\n")
        
        # Get next question number
        tracker = QuestionTracker()
        question_number = tracker.get_next_number()
        sys.stderr.write(f"Using question number: {question_number}\n")
        
        # Step 1: Analyze the problem
        sys.stderr.write("Starting analysis...\n")
        analysis_result = analyze_financial_problem({"problem_text": problem_text})
        if not analysis_result.get('success', False):
            sys.stderr.write(f"Analysis failed: {analysis_result}\n")
            return {
                'success': False,
                'error': f"Analysis failed: {analysis_result.get('error', 'Unknown error')}"
            }
        sys.stderr.write("Analysis complete.\n")
        
        # Step 2: Solve the problem
        sys.stderr.write("Starting solution...\n")
        solve_result = solve_financial_problem(analysis_result)
        if not solve_result.get('success', False):
            sys.stderr.write(f"Solution failed: {solve_result}\n")
            return {
                'success': False,
                'error': f"Solution failed: {solve_result.get('error', 'Unknown error')}"
            }
        sys.stderr.write("Solution complete.\n")
        
        # Step 3: Generate Excel instructions
        sys.stderr.write("Generating instructions...\n")
        instruction_result = generate_excel_instructions(problem_text, question_number)
        if not instruction_result.get('success', False):
            sys.stderr.write(f"Instruction generation failed: {instruction_result}\n")
            return {
                'success': False,
                'error': f"Instruction generation failed: {instruction_result.get('error', 'Unknown error')}"
            }
        sys.stderr.write("Instructions generated.\n")
        
        # Step 4: Write instructions to file
        sys.stderr.write("Writing instructions to file...\n")
        write_result = write_instructions_to_file(instruction_result['instructions'], question_number)
        if not write_result.get('success', False):
            sys.stderr.write(f"Writing instructions failed: {write_result}\n")
            return {
                'success': False,
                'error': f"Writing instructions failed: {write_result.get('error', 'Unknown error')}"
            }
        sys.stderr.write(f"Instructions written to: {write_result['file']}\n")
        
        # Return comprehensive results
        return {
            'success': True,
            'question_number': question_number,
            'analysis': analysis_result,
            'solution': solve_result,
            'instructions_file': write_result['file'],
            'instructions': instruction_result['instructions']
        }
        
    except Exception as e:
        sys.stderr.write(f"Unexpected error: {str(e)}\n")
        return {
            'success': False,
            'error': str(e)
        }

def main():
    if len(sys.argv) != 3:
        json.dump({
            'success': False,
            'error': 'Usage: process_financial_problem.py <command> <json_args>'
        }, sys.stdout)
        sys.exit(1)
        
    command = sys.argv[1]
    try:
        args = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error parsing arguments: {str(e)}\n")
        json.dump({
            'success': False,
            'error': 'Invalid JSON arguments'
        }, sys.stdout)
        sys.exit(1)
    
    if command != 'process_financial_problem':
        sys.stderr.write(f"Unknown command: {command}\n")
        json.dump({
            'success': False,
            'error': f'Unknown command: {command}'
        }, sys.stdout)
        sys.exit(1)
        
    result = process_financial_problem(args)
    json.dump(result, sys.stdout)

if __name__ == '__main__':
    main()