# DevRelAgent Capabilities

## What DevRelAgent Can Do

### Core Capabilities

#### 1. **Database Query & Analysis**
- Query ClickHouse databases using natural language
- Analyze logs, metrics, and traces
- Identify patterns, anomalies, and trends in observability data
- Generate statistics and summaries from data
- **Tools**: `clickhouse_query`, `get_error_rate`, `get_top_errors`, `get_latency_metrics`

#### 2. **Code Search & Analysis**
- Search codebases for functions, classes, and implementations
- Find specific code patterns and usages
- Locate authentication, authorization, and API implementations
- Understand how features are implemented
- **Tools**: `code_search`, `get_file_content`

#### 3. **Documentation Search**
- Search technical documentation and guides
- Find API documentation and usage examples
- Locate setup and configuration guides
- Access README files and deployment guides
- **Tools**: `rag_search`, `doc_search`

#### 4. **Incident Investigation**
- Investigate system issues and outages
- Analyze error rates and performance degradation
- Correlate errors with traces and logs
- Identify root causes of problems
- **Tools**: `correlate_error_with_traces`, `get_error_rate`, `get_latency_metrics`

#### 5. **Configuration Generation**
- Generate OpenTelemetry configuration files
- Create monitoring dashboard configurations
- Set up logging configurations
- Generate deployment configs
- **Tools**: `generate_config`, `generate_opentelemetry_config`

#### 6. **Dashboard Management**
- Create monitoring dashboards for services
- Set up custom metric visualizations
- Build service health dashboards
- Configure alert thresholds
- **Tools**: `create_dashboard`, `get_dashboard`

#### 7. **Issue & Ticket Management**
- Draft GitHub issues and pull requests
- Create structured bug reports
- Generate feature request templates
- Report documentation gaps
- **Tools**: `draft_github_issue`, `draft_github_pr`, `create_structured_ticket`, `create_gap_tickets`

#### 8. **Gap Detection**
- Identify missing documentation
- Find undocumented features
- Detect gaps in API documentation
- Suggest areas needing improvement
- **Tools**: `detect_documentation_gaps`

### Advanced Features

#### **Intent Classification with Confidence Scoring**
- Classifies user queries into 10+ intent categories
- Provides confidence scores (0.0-1.0) for each classification
- Falls back to suggestions when confidence is low
- Prevents execution of unclear requests

#### **Explain-Before-Act**
- Explains planned actions before executing tools
- Shows reasoning and expected outcomes
- Indicates risk level for approval-required actions
- Helps users understand what will happen

#### **Structured Outputs**
- Returns structured responses with observations
- Provides confidence levels and certainty assessments
- Includes evidence supporting conclusions
- Suggests next steps and actions

#### **Comprehensive Audit Trail**
- Logs all user interactions and tool executions
- Tracks data access and approvals
- Provides export capabilities (JSON/CSV)
- Supports compliance and security audits

## What DevRelAgent Cannot Do

### Unsupported Actions

#### **Direct System Modifications**
- ❌ Cannot directly modify system configurations
- ❌ Cannot execute arbitrary code on servers
- ❌ Cannot make changes without approval (for risky actions)
- ❌ Cannot access credentials or secrets

#### **Unauthorized Data Access**
- ❌ Cannot access data outside configured sources
- ❌ Cannot bypass authentication/authorization
- ❌ Cannot access other users' data
- ❌ Cannot read sensitive files without approval

#### **Interactive Actions**
- ❌ Cannot browse the web interactively (without approval)
- ❌ Cannot execute browser automation (without approval)
- ❌ Cannot perform write operations (without approval)
- ❌ Cannot delete data (without approval)

#### **Out-of-Scope Tasks**
- ❌ Cannot perform tasks unrelated to DevRel/engineering
- ❌ Cannot answer questions about unrelated topics
- ❌ Cannot provide personal opinions or recommendations
- ❌ Cannot execute tasks requiring human judgment

### Technical Limitations

#### **Knowledge Cutoff**
- Training data has a knowledge cutoff date
- May not be aware of very recent changes
- Documentation indexes require periodic updates

#### **Tool Dependencies**
- Requires ClickHouse to be accessible for database queries
- Requires indexed codebases for code search
- Requires indexed documentation for doc search
- External tools may have their own limitations

#### **Performance Constraints**
- Large database queries may timeout
- Complex analyses may take time
- Rate limits apply to external API calls
- Concurrent requests are limited

#### **Accuracy Considerations**
- Natural language queries may be ambiguous
- Code search relies on embeddings (imperfect matching)
- Documentation may be outdated or incomplete
- LLM-generated responses may contain errors

## Risk Levels & Approval Requirements

### **Low Risk** (No Approval Required)
- Reading documentation
- Searching code
- Querying databases (read-only)
- Generating configurations

### **Medium Risk** (Approval Required)
- Creating GitHub issues
- Drafting pull requests
- Generating reports

### **High Risk** (Approval Required)
- Browser automation
- Write operations
- Schema modifications

### **Critical Risk** (Approval Required)
- Delete operations
- Production system changes
- Credential access

## Usage Guidelines

### Best Practices
1. **Be Specific**: Provide clear, detailed queries
2. **Use Examples**: Reference specific files, functions, or error messages
3. **Review Explanations**: Check the "explain-before-act" output
4. **Verify Results**: Cross-check important information
5. **Provide Feedback**: Report incorrect responses for improvement

### When to Use DevRelAgent
- ✅ Investigating production issues
- ✅ Searching for code implementations
- ✅ Analyzing logs and metrics
- ✅ Finding documentation
- ✅ Generating configurations
- ✅ Creating tickets and issues

### When Not to Use DevRelAgent
- ❌ Emergency incident response (use established procedures)
- ❌ Production system changes (use proper change management)
- ❌ Security incidents (follow security protocols)
- ❌ Tasks requiring human judgment or approval
- ❌ Questions outside the DevRel/engineering domain

## Extending Capabilities

### Adding New Tools
Tools can be added by:
1. Creating a new tool module in `apps/backend/tools/`
2. Implementing the tool interface
3. Registering with the tool registry
4. Adding appropriate guardrails

### Adding New Intents
Intents can be added by:
1. Updating `agent/router.py` with new intent definitions
2. Adding examples and keywords
3. Mapping to appropriate tools
4. Testing classification accuracy

### Customizing Guardrails
Guardrails can be customized by:
1. Modifying input/output validation rules
2. Adding new check types
3. Adjusting risk levels
4. Configuring approval requirements

## Support & Feedback

For issues, questions, or feedback:
- GitHub Issues: [Project Repository]
- Documentation: [Project Wiki]
- Support Channel: [Team Communication Channel]
