#!/usr/bin/env node
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ErrorCode,
  McpError,
} from '@modelcontextprotocol/sdk/types.js';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

class ExcelServer {
  constructor() {
    this.server = new Server(
      {
        name: 'excel-master',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupTools();
    
    // Error handling
    this.server.onerror = (error) => console.error('[MCP Error]', error);
    process.on('SIGINT', async () => {
      await this.server.close();
      process.exit(0);
    });
  }

  setupTools() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: [
        {
          name: 'read_worksheet',
          description: 'Read data from an Excel worksheet',
          inputSchema: {
            type: 'object',
            properties: {
              file_path: {
                type: 'string',
                description: 'Path to the Excel file',
              },
              sheet_name: {
                type: 'string',
                description: 'Name of the worksheet to read',
              },
              range: {
                type: 'string',
                description: 'Optional range to read (e.g., "A1:B10")',
              },
            },
            required: ['file_path', 'sheet_name'],
          },
        },
        {
          name: 'write_worksheet',
          description: 'Write data to an Excel worksheet',
          inputSchema: {
            type: 'object',
            properties: {
              file_path: {
                type: 'string',
                description: 'Path to the Excel file',
              },
              sheet_name: {
                type: 'string',
                description: 'Name of the worksheet to write to',
              },
              range: {
                type: 'string',
                description: 'Starting cell or range to write to (e.g., "A1")',
              },
              data: {
                type: 'array',
                description: 'Data to write (2D array)',
                items: {
                  type: 'array',
                  items: {
                    type: ['string', 'number', 'boolean', 'null'],
                  },
                },
              },
            },
            required: ['file_path', 'sheet_name', 'range', 'data'],
          },
        },
        {
          name: 'create_workbook',
          description: 'Create a new Excel workbook',
          inputSchema: {
            type: 'object',
            properties: {
              file_path: {
                type: 'string',
                description: 'Path where to create the Excel file',
              },
              sheets: {
                type: 'array',
                description: 'List of sheet names to create',
                items: {
                  type: 'string',
                },
              },
            },
            required: ['file_path'],
          },
        },
        {
          name: 'process_financial_problem',
          description: 'Process a financial problem through analysis, solution, and Excel instruction generation',
          inputSchema: {
            type: 'object',
            properties: {
              problem_text: {
                type: 'string',
                description: 'The financial problem text to process'
              }
            },
            required: ['problem_text']
          }
        }
      ],
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const scriptPath = path.join(__dirname, 
        request.params.name === 'process_financial_problem' 
          ? 'process_financial_problem.py' 
          : 'excel_operations.py'
      );
      
      const pythonProcess = spawn('python3', [
        scriptPath,
        request.params.name,
        JSON.stringify(request.params.arguments),
      ]);

      return new Promise((resolve, reject) => {
        let output = '';
        let error = '';

        pythonProcess.stdout.on('data', (data) => {
          output += data.toString();
        });

        pythonProcess.stderr.on('data', (data) => {
          error += data.toString();
        });

        pythonProcess.on('close', (code) => {
          if (code === 0) {
            try {
              const result = JSON.parse(output);
              if (!result.success) {
                reject(new McpError(ErrorCode.InternalError, result.error));
                return;
              }
              resolve({
                content: [
                  {
                    type: 'text',
                    text: JSON.stringify(result, null, 2),
                  },
                ],
              });
            } catch (e) {
              reject(new McpError(ErrorCode.InternalError, `Invalid JSON output: ${output}`));
            }
          } else {
            reject(new McpError(ErrorCode.InternalError, `Python script error: ${error}`));
          }
        });
      });
    });
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Excel MCP server running on stdio');
  }
}

const server = new ExcelServer();
server.run().catch(console.error);