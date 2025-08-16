# MCP Integration Testing Checklist

## ✅ Prerequisites

- [ ] Python 3.10+ installed
- [ ] MassGen project environment set up (uv venv)
- [ ] Claude Code SDK installed
- [ ] All MCP module files created

## 🧪 Unit Testing

### MCP Client Testing
- [ ] Basic connection testing
- [ ] Tool discovery testing  
- [ ] Tool invocation testing
- [ ] Error handling testing
- [ ] Disconnect and reconnection testing

### Claude Code Backend Testing
- [ ] MCP server initialization
- [ ] Tool list integration
- [ ] MCP tool call routing
- [ ] System prompt enhancement
- [ ] Cleanup and disconnection

## 🔗 Integration Testing

### Simple Integration Testing
```bash
# 1. Test MCP client
python test_mcp_integration.py

# 2. Test error handling
python test_mcp_error_handling.py
```

### Claude Code + MCP Testing
```bash
# Single agent testing
uv run python -m massgen.cli --config massgen/configs/claude_code_simple_mcp.yaml "Use MCP tools to: 1) echo 'Hello MCP', 2) add 42+58, 3) get current time"

# Multi-agent testing
uv run python -m massgen.cli --config massgen/configs/two_agents_mcp_test.yaml "Compare MCP calculation tools vs web search capabilities"
```

## 🎯 Functionality Verification

### Basic Functionality
- [ ] MCP server auto-connection
- [ ] Tool auto-discovery and registration
- [ ] Correct tool name prefix (mcp__<server>__<tool>)
- [ ] Tool calls execute successfully
- [ ] Results returned correctly

### Advanced Functionality  
- [ ] Multiple MCP server support
- [ ] Concurrent tool calls
- [ ] Error recovery and retry
- [ ] Resource cleanup and connection management

### Interactive Testing
- [ ] Use MCP tools in interactive mode
- [ ] Available MCP tools shown in system prompt
- [ ] Tool call results display correctly
- [ ] Error messages are user-friendly

## 🔍 Edge Case Testing

### Error Scenarios
- [ ] MCP server unavailable
- [ ] Invalid tool names
- [ ] Wrong parameter types
- [ ] Network connection interruption
- [ ] Server crash recovery

### Performance Testing
- [ ] High volume tool calls
- [ ] Long-running stability
- [ ] Memory usage
- [ ] Connection pool effectiveness

## 🚀 End-to-End Testing

### Real-world Scenario Testing
1. **File Operation Scenario**
   ```bash
   "Use MCP filesystem tools to create a Python script, run it, and show results"
   ```

2. **Data Processing Scenario**  
   ```bash
   "Calculate the sum of numbers 1-100 using MCP math tools"
   ```

3. **Multi-tool Collaboration Scenario**
   ```bash
   "Get current time, create a timestamp file, and echo the filename"
   ```

### Multi-agent Collaboration
- [ ] MCP tool information shared between agents
- [ ] Different agents use the same MCP server
- [ ] MCP results used in multi-agent coordination

## 📊 Test Results Recording

### Test Environment
- Operating System: ________________
- Python Version: _______________
- MassGen Version: ______________
- Test Date: _________________

### Test Results
- [ ] All unit tests passed
- [ ] Integration tests error-free
- [ ] Functionality verification completed
- [ ] Performance meets expectations
- [ ] Error handling correct

### Issue Log
1. Issue Description: ___________________
   Solution: ___________________
   
2. Issue Description: ___________________
   Solution: ___________________

## 🔧 Troubleshooting

### Common Issues
1. **MCP Server Connection Failed**
   - Check if command path is correct
   - Verify Python environment and dependencies
   - Review server output logs

2. **Tool Call Failed**
   - Confirm tool name is correct (with prefix)
   - Check parameter format and types
   - Review MCP server error messages

3. **Performance Issues**
   - Check MCP server response time
   - Monitor memory and CPU usage
   - Consider connection pool and cache optimization

### Debugging Tips
- Enable verbose logging: `logging_enabled: true`
- Use simple test server to verify basic functionality
- Gradually increase complexity for testing
- Use Python debugger to inspect MCP communication

## ✅ Sign-off Confirmation

Test Engineer: ____________________
Date: ____________________________
Status: [ ] Passed [ ] Needs Fix [ ] Needs Retest