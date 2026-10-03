# DevRelAgent Security Model

## Overview

DevRelAgent implements a defense-in-depth security approach with multiple layers of protection to ensure safe, controlled, and auditable AI operations in production environments.

## Security Architecture

### Layer 0: Authentication & Tenant Isolation (Phase 1)

- **Pluggable identity**: `AUTH_PROVIDER=dev` derives the caller from headers
  (development/tests only); `AUTH_PROVIDER=clerk` verifies a real Clerk/OIDC JWT
  against the issuer's JWKS (signature, issuer and audience).
- **Workspace → Project scoping**: every request resolves to a workspace and a
  project. Queries are always filtered by the caller's workspace, so another
  tenant's id resolves to `404`, never to data.
- **Roles**: memberships carry `owner` / `admin` / `member` / `viewer`; the
  workspace creator owns it. Administrative endpoints require `owner`/`admin`.
- **Project API keys**: `drk_<prefix>_<secret>`; only a salted SHA-256 hash is
  stored. Keys authenticate data-plane access and are denied administrative
  actions.
- **Session store**: conversation state is namespaced per project and held in a
  shared store (`memory` / `redis`).

**Implementation**: `auth/`, `db/`, `sessions/`

### Layer 1: Input Validation & Sanitization

#### **Input Guardrails**
- **Topic Filtering**: Blocks off-topic and inappropriate queries
- **PII Detection**: Identifies and redacts personally identifiable information
- **Injection Prevention**: Detects SQL injection, prompt injection, and code injection attempts
- **Content Sanitization**: Removes malicious patterns and unsafe content

**Implementation**: `guardrails/input_guard.py`

```python
# Example: Input validation flow
user_input → topic_check → pii_detection → injection_check → sanitized_input
```

**Security Controls**:
- Rejects queries unrelated to DevRel/engineering
- Redacts sensitive data (passwords, tokens, personal info)
- Blocks suspicious patterns (SQL injection, XSS, command injection)
- Limits input length to prevent DoS

### Layer 2: Intent Classification & Enforcement

#### **Strict Intent Enforcement**
- **Confidence Scoring**: Classifies intents with confidence scores (0.0-1.0)
- **Low Confidence Handling**: Rejects or provides suggestions for unclear queries
- **Unknown Intent Detection**: Blocks unsupported request types
- **Fallback Suggestions**: Provides helpful alternatives for unclear requests

**Implementation**: `agent/router.py`

**Security Controls**:
- Blocks execution when confidence < 0.6
- Returns helpful suggestions for low-confidence queries
- Prevents "hallucinated" tool usage
- Logs all confidence scores for monitoring

### Layer 3: Tool Execution Controls

#### **Tool Guardrails**
- **Rate Limiting**: Prevents tool abuse and resource exhaustion
- **Timeout Protection**: Limits execution time for each tool
- **Scope Restriction**: Limits tools to authorized operations only
- **Resource Limits**: Controls memory, CPU, and network usage

**Implementation**: `guardrails/tool_guard.py`

**Security Controls**:
```python
# Risk levels by tool category
RISK_LEVELS = {
    "read_only": "low",           # No approval required
    "api": "medium",               # Requires approval
    "write": "high",               # Requires approval
    "critical": "critical",         # Requires approval + verification
}
```

### Layer 4: Human-in-the-Loop (HITL)

#### **Approval Workflow**
- **Risk-Based Approvals**: High-risk actions require explicit approval
- **Approval Requests**: Detailed plans sent for review before execution
- **Timeout Handling**: Auto-rejects if no response within timeout period
- **Approval History**: Complete audit trail of all decisions

**Implementation**: `guardrails/approval_guard.py`

**Approval-Required Actions**:
- Browser automation (CRITICAL)
- Write operations (HIGH)
- Schema changes (HIGH)
- GitHub PR creation (MEDIUM)
- GitHub issue creation (MEDIUM)

**Workflow**:
```
Tool Request → Risk Assessment → Approval Required? → Yes: Request Approval → Execute/Reject
                                         → No: Execute Directly
```

### Layer 5: Output Validation

#### **Output Guardrails**
- **SQL Safety**: Validates SQL queries for dangerous operations
- **Grounding Check**: Ensures responses are grounded in tool results
- **HITL Gate**: Requires approval for sensitive outputs
- **Content Filtering**: Removes inappropriate or unsafe content

**Implementation**: `guardrails/output_guard.py`

**Security Controls**:
- Blocks DROP, DELETE, TRUNCATE in SQL queries
- Validates claims against tool results
- Flags ungrounded or hallucinated content
- Sanitizes output for safe display

### Layer 6: Comprehensive Audit Trail

#### **Audit Logging**
- **Complete Logging**: All actions logged with full context
- **Append-only files**: JSONL audit logs written per day
- **Data Access Tracking**: Monitors all data source access
- **Export Capabilities**: JSON and CSV export
- **Not yet implemented**: content hashing / tamper evidence

**Implementation**: `audit/logger.py`

**Logged Events**:
- All user queries and responses
- Tool executions with arguments and results
- Approval requests and decisions
- Guardrail triggers and blocks
- Data access events
- Errors and exceptions

**Audit Data**:
```json
{
  "audit_id": "audit_20260311120000",
  "timestamp": "2026-03-11T12:00:00Z",
  "session_id": "sess_abc123",
  "user_id": "user@example.com",
  "action_type": "tool_call",
  "tool_name": "clickhouse_query",
  "tool_arguments": {"natural_query": "Show recent errors"},
  "tool_success": true,
  "data_accessed": [{"source": "clickhouse", "query_type": "read"}],
  "guardrail_result": "passed",
  "approval_decision": null,
  "confidence_score": 0.95
}
```

## Security Policies

### Data Protection

#### **Sensitive Data Handling**
- **PII Redaction**: Automatically detects and redacts PII
- **Credential Protection**: Never logs passwords, tokens, or keys
- **Data Sanitization**: Sanitizes all logged data
- **Secure Storage**: Audit logs stored with restricted access

#### **Data Access Control**
- **Source Restrictions**: Only accesses configured data sources
- **Read-Only Default**: Default tools are read-only
- **Approval for Writes**: Write operations require approval
- **Tenant Isolation**: requests are scoped to a workspace + project; cross-tenant access is denied

### Authentication & Authorization

#### **Access Control**
- **Authentication**: pluggable (dev headers locally, Clerk/OIDC JWTs in real deployments)
- **Authorization**: role checks (`owner`/`admin`/`member`/`viewer`) via `require_role`
- **Session Management**: sessions are unique and namespaced per project
- **Audit Attribution**: actions attributed to a session and user
- **Durable, tenant-scoped records**: audit entries and approval decisions are
  persisted per project and survive restarts; reads are always scoped
- **Shared, tenant-scoped limits**: rate-limit windows, token budgets and
  circuit breakers live in a shared state backend and are keyed per project, so
  every replica enforces the same limits
- **Remaining gap**: an approval decision must be resolved by the process that
  is waiting for it (the in-process signal is not yet shared via pub/sub)

#### **API Security**
- **CORS Configuration**: Controlled cross-origin access
- **Rate Limiting**: Tool-level limits exist; no HTTP edge limit yet
- **Input Validation**: All API inputs validated (Pydantic)
- **Error Handling**: Validation errors are returned without internal details
- **Authentication**: required on all data endpoints (401 without valid credentials)
- **Remaining gap**: no HTTP edge rate limiting yet (tool-level limits exist)

### Threat Mitigation

#### **Prompt Injection**
- **Input Sanitization**: Removes malicious prompt patterns
- **Context Isolation**: Separates user input from system prompts
- **Output Validation**: Validates responses against context
- **Instruction Filtering**: Filters instructions embedded in queries

#### **Data Exfiltration**
- **Query Limits**: Limits amount of data returned
- **Result Filtering**: Sanitizes query results
- **Access Logging**: Logs all data access
- **Network Restrictions**: Controls external network access

#### **Resource Exhaustion**
- **Rate Limiting**: Limits request frequency, shared across replicas and scoped per project
- **Timeouts**: All operations have timeouts
- **Memory Limits**: Constrains memory usage
- **Concurrency Limits**: Limits concurrent operations

#### **Code Execution**
- **No Arbitrary Code**: Cannot execute arbitrary user code
- **Tool Whitelisting**: Only approved tools available
- **Sandboxed Execution**: Tools run in controlled environment
- **Approval Gates**: Dangerous operations require approval

## Compliance & Governance

> **No certification is claimed.** DevRelAgent is not SOC 2, HIPAA, GDPR or
> PCI DSS certified, and nothing in this document should be read as a
> compliance guarantee. It describes controls that *help* with compliance work
> and the gaps that remain.

### Controls That Support Compliance

- **PII detection and redaction** on user input
- **Audit logging** of queries, tool calls and approval decisions
- **Approval gates** for risky, write-like actions
- **Data-access logging** for configured datasources

### Known Gaps

- **Approval decisions are not yet resolvable across worker processes** (the waiting signal is in-process; the records themselves are durable)
- **`AUTH_PROVIDER=dev` trusts caller-supplied headers** and must never face an untrusted network
- **No tamper-evident / hash-chained audit log**
- **No configurable retention or right-to-erasure tooling**
- **No encryption-at-rest story** for stored audit files
- **No HTTP edge rate limiting**

#### **Audit Features**
- **Append-only files**: JSONL audit trail
- **Export & Reporting**: JSON/CSV export capabilities

### Governance Controls

#### **Multi-Tenancy**
- **Tenant Isolation**: separate system-of-record data per workspace, enforced in the API
- **User-Tenant Mapping**: memberships associate users with workspaces and roles
- **Projects**: the working scope within a workspace (projects, API keys, sessions)
- **Remaining gap**: per-tenant resource quotas

#### **Policy Enforcement**
- **Approval Policies**: Configurable approval requirements
- **Access Policies**: Role-based access control
- **Data Policies**: Data handling and retention policies
- **Monitoring Policies**: Continuous monitoring and alerting

## Security Best Practices

### Deployment Security

#### **Production Hardening**
1. **Environment Variables**: Store secrets in environment variables
2. **Network Isolation**: Deploy in isolated network segment
3. **TLS/SSL**: Encrypt all network traffic
4. **Firewall Rules**: Restrict ingress/egress traffic
5. **Container Security**: Use minimal, secure base images

#### **Secrets Management**
- Never hardcode credentials
- Use secure secret stores (Vault, AWS Secrets Manager)
- Rotate credentials regularly
- Audit all credential access

### Operational Security

#### **Monitoring**
- **Audit Log Monitoring**: Review logs regularly
- **Anomaly Detection**: Alert on unusual patterns
- **Performance Metrics**: Monitor system health
- **Security Events**: Alert on security-relevant events

#### **Incident Response**
- **Playbooks**: Documented response procedures
- **Escalation**: Clear escalation paths
- **Forensics**: Preserve audit logs for investigation
- **Post-Mortem**: Learn from incidents

### Development Security

#### **Secure Development**
- **Code Review**: All code changes reviewed
- **Security Testing**: Include security tests
- **Dependency Scanning**: Scan for vulnerabilities
- **Penetration Testing**: Regular security assessments

#### **Configuration Management**
- **Version Control**: Track all configuration changes
- **Change Management**: Approve all production changes
- **Backup & Recovery**: Regular backups and tested recovery
- **Disaster Recovery**: Documented and tested DR procedures

## Security Checklist

### Pre-Deployment
- [ ] All input guardrails enabled
- [ ] All output guardrails enabled
- [ ] Tool guardrails configured
- [ ] Approval workflow enabled for risky actions
- [ ] Audit logging enabled and configured
- [ ] TLS/SSL enabled
- [x] Rate limiting configured (shared state backend + per-project scoping)
- [ ] Secrets properly configured
- [ ] Network restrictions in place
- [ ] Monitoring and alerting configured

### Post-Deployment
- [ ] Review audit logs daily (first week)
- [ ] Monitor confidence scores
- [ ] Track approval rates
- [ ] Monitor guardrail triggers
- [ ] Review tool execution patterns
- [ ] Check for anomalous behavior
- [ ] Validate security controls
- [ ] Test incident response procedures

## Incident Reporting

### Security Incidents
For security incidents, report to:
- **Security Team**: security@example.com
- **Incident Response**: incidents@example.com
- **Urgent**: +1-XXX-XXX-XXXX (24/7)

### Vulnerability Disclosure
To report vulnerabilities:
- **Responsible Disclosure**: security@example.com
- **PGP Key**: Available on request
- **Response Time**: Within 48 hours

## References

- [OWASP AI Security](https://owasp.org/www-project-ai-security/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [ISO 27001](https://www.iso.org/standard/27001)
- [SOC 2 Criteria](https://www.aicpa.org/soc4so)
