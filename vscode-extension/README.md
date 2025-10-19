# MassGen - Multi-Agent AI Assistant for VSCode

**MassGen** brings the power of collaborative multi-agent AI directly into Visual Studio Code. Multiple frontier AI models (GPT, Claude, Gemini, etc.) work together to solve your coding challenges.

## ✨ Features

- **🤝 Multi-Agent Collaboration**: Multiple AI models work in parallel on your questions
- **💬 Interactive Chat**: Natural conversation interface with real-time streaming
- **🔍 Code Analysis**: Select code and get insights from multiple AI perspectives
- **🎯 Smart Integration**: Seamlessly integrated into VSCode workflow
- **⚡ Real-time Updates**: Watch agents collaborate and converge on solutions

## 📋 Prerequisites

1. **Python 3.11+** installed
2. **MassGen Python package** installed:
   ```bash
   pip install massgen
   ```

3. **API Keys** configured in your `.env` file or environment:
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_API_KEY`
   - etc.

## 🚀 Quick Start

1. **Install the extension** from VSCode Marketplace (or install manually)

2. **Open Command Palette** (`Cmd+Shift+P` / `Ctrl+Shift+P`)

3. **Run** `MassGen: Start Chat`

4. **Ask anything!** Multiple AI agents will collaborate on your question

## 💡 Usage

### Chat with Multiple Agents

1. Click the MassGen icon in the status bar, or
2. Run `MassGen: Start Chat` from Command Palette
3. Type your question and press Enter

### Analyze Code

1. Select code in your editor
2. Right-click → `MassGen: Analyze Code Selection`, or
3. Run command from Command Palette

### Test Connection

Run `MassGen: Test Connection` to verify everything is working.

## ⚙️ Configuration

Configure MassGen in VSCode Settings (`Cmd+,` / `Ctrl+,`):

- **Python Path**: Path to Python executable with MassGen installed
- **Default Config**: Path to your default MassGen configuration file
- **Enable Logging**: Show detailed logs in Output panel

## 🔧 Development

### Building from Source

```bash
cd vscode-extension
npm install
npm run compile
```

### Running in Debug Mode

1. Open `vscode-extension` folder in VSCode
2. Press `F5` to launch Extension Development Host
3. Test the extension in the new window

## 📝 Commands

| Command | Description |
|---------|-------------|
| `MassGen: Start Chat` | Open interactive chat panel |
| `MassGen: Analyze Code Selection` | Analyze selected code |
| `MassGen: Configure Agents` | Open configuration UI |
| `MassGen: Test Connection` | Test Python backend connection |

## 🐛 Troubleshooting

### Extension won't activate

- Make sure MassGen is installed: `python -m pip show massgen`
- Check Python path in settings
- View logs: `Output` panel → `MassGen`

### Connection errors

- Verify API keys are configured
- Run `MassGen: Test Connection`
- Check the Output panel for errors

## 📚 Learn More

- [MassGen Documentation](https://docs.massgen.io)
- [GitHub Repository](https://github.com/Leezekun/MassGen)
- [Report Issues](https://github.com/Leezekun/MassGen/issues)

## 📄 License

Apache 2.0 - See LICENSE file for details

---

Made with ❤️ by the MassGen team
