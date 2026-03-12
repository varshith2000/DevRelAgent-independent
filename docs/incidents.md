# DevRelAgent Incident Scenarios

This document describes real-world incident scenarios that DevRelAgent can help investigate and resolve. These scenarios demonstrate the agent's capabilities in production environments.

## Incident 1: API Error Rate Spike

### Scenario Description

**Date**: March 10, 2026, 14:32 UTC
**Severity**: High
**Duration**: 45 minutes
**Impact**: 5,000 users affected, 15% error rate

### Initial Detection

**Alert**: Monitoring dashboard showed API error rate increased from 2% to 15% within 10 minutes.

**Initial Query to DevRelAgent**:
```
Why is the API error rate suddenly high?
```

### Investigation Process

#### Step 1: Query Error Data
```
Show me recent API errors from the last hour
```

**DevRelAgent Actions**:
- Executed ClickHouse query to fetch error logs
- Filtered by API service and timestamp
- Identified top error types

**Results**:
```
Top Errors:
- DatabaseConnectionTimeout: 234 occurrences
- QueryExecutionFailed: 156 occurrences
- RequestTimeout: 89 occurrences
```

#### Step 2: Analyze Error Patterns
```
Analyze the database connection timeout errors
```

**DevRelAgent Actions**:
- Correlated errors with database metrics
- Checked connection pool usage
- Examined query performance

**Observations**:
- Connection pool exhaustion detected
- Average query time increased from 150ms to 450ms
- Database CPU utilization at 95%

#### Step 3: Root Cause Analysis
```
What caused the database performance degradation?
```

**DevRelAgent Actions**:
- Queried slow query logs
- Analyzed query patterns
- Checked for schema changes

**Findings**:
```
Root Cause: Recent deployment introduced a new query without proper indexing
- Query: SELECT * FROM user_activity WHERE DATE(created_at) = '2026-03-10'
- Execution time: 4.5 seconds (vs. 150ms baseline)
- Frequency: 500+ requests per minute
```

### Resolution

**Immediate Action**:
```
Generate a rollback plan for the recent deployment
```

**DevRelAgent Output**:
```yaml
Rollback Plan:
  1. Identify deployment: api-v2.4.3 (deployed 14:15 UTC)
  2. Revert to previous version: api-v2.4.2
  3. Verify connection pool metrics
  4. Monitor error rates for 15 minutes

Command:
  kubectl rollout undo deployment/api
```

**Long-term Fix**:
```
Create a GitHub issue for the indexing problem
```

**DevRelAgent Created**:
- GitHub issue with query analysis
- Recommended index creation
- Performance testing guidelines

### Lessons Learned

**What Went Well**:
- Rapid identification of database as root cause
- Clear correlation between deployment and errors
- Automated rollback plan generation

**Areas for Improvement**:
- Pre-deployment query performance checks needed
- Database monitoring thresholds too high
- Index review process required

### Preventive Measures Implemented

1. **Query Review Gate**: All new queries must be reviewed for performance
2. **Automated Testing**: Performance tests for database queries in CI/CD
3. **Monitoring Enhancement**: Lower thresholds for query execution time
4. **Index Management**: Regular index usage analysis

---

## Incident 2: Authentication Service Outage

### Scenario Description

**Date**: March 8, 2026, 09:15 UTC
**Severity**: Critical
**Duration**: 2 hours
**Impact**: Complete login failure for all users

### Initial Detection

**Alert**: Zero successful logins for 5 minutes

**Initial Query to DevRelAgent**:
```
Why can't users log in?
```

### Investigation Process

#### Step 1: Check Authentication Service Health
```
Show me the authentication service status and recent errors
```

**DevRelAgent Actions**:
- Queried authentication logs
- Checked service health endpoints
- Analyzed error patterns

**Results**:
```
Authentication Service Status: CRITICAL
- Successful logins (last hour): 0
- Failed logins (last hour): 12,456
- Top error: "Invalid JWT signature" (100% of failures)
```

#### Step 2: Investigate JWT Configuration
```
Search for JWT configuration changes in the last 24 hours
```

**DevRelAgent Actions**:
- Searched configuration files
- Checked deployment history
- Reviewed environment variables

**Findings**:
```
Issue Detected: JWT secret rotation at 09:00 UTC
- New secret: ROTATED_SECRET_2026
- Old secret: ORIGINAL_SECRET_2025
- Problem: Services not synchronized
```

#### Step 3: Identify Affected Services
```
Which services are using the old JWT secret?
```

**DevRelAgent Actions**:
- Searched codebase for JWT secret usage
- Checked service configurations
- Identified deployment status

**Results**:
```
Services Using Old Secret:
- api-gateway: Using new secret ✓
- auth-service: Using new secret ✓
- user-service: Using OLD secret ✗
- notification-service: Using OLD secret ✗
```

### Resolution

**Immediate Action**:
```
Generate configuration updates for services using the old secret
```

**DevRelAgent Output**:
```yaml
Emergency Fix:
  Services to Update:
    - name: user-service
      config: JWT_SECRET=ROTATED_SECRET_2026
      restart_required: true

    - name: notification-service
      config: JWT_SECRET=ROTATED_SECRET_2026
      restart_required: true

  Commands:
    - kubectl set env deployment/user-service JWT_SECRET=ROTATED_SECRET_2026
    - kubectl rollout restart deployment/user-service
    - kubectl set env deployment/notification-service JWT_SECRET=ROTATED_SECRET_2026
    - kubectl rollout restart deployment/notification-service
```

**Verification**:
```
Monitor login success rate after configuration update
```

**DevRelAgent Monitored**:
```json
{
  "09:45 UTC": "Login success rate: 0%",
  "09:50 UTC": "Login success rate: 45% (user-service updated)",
  "09:55 UTC": "Login success rate: 98% (notification-service updated)",
  "10:00 UTC": "Login success rate: 100% (all services recovered)"
}
```

### Lessons Learned

**What Went Well**:
- Rapid identification of JWT secret issue
- Clear mapping of affected services
- Automated fix generation

**Areas for Improvement**:
- Secret rotation process not synchronized
- No validation after secret rotation
- Monitoring didn't detect configuration mismatch

### Preventive Measures Implemented

1. **Synchronized Rotation**: Atomic secret updates across all services
2. **Validation Checks**: Post-rotation validation of all services
3. **Configuration Drift Detection**: Monitor for configuration mismatches
4. **Rollback Plan**: Quick rollback procedure for secret rotations

---

## Incident 3: Memory Leak in Background Worker

### Scenario Description

**Date**: March 5, 2026, 02:00 UTC
**Severity**: Medium
**Duration**: 12 hours (gradual degradation)
**Impact**: Slow response times, eventually OOM kills

### Initial Detection

**Alert**: Background worker restarted due to OOM (Out of Memory)

**Initial Query to DevRelAgent**:
```
Why did the background worker crash?
```

### Investigation Process

#### Step 1: Check Worker Logs and Metrics
```
Show me the background worker memory usage and crash details
```

**DevRelAgent Actions**:
- Queried Grafana metrics
- Analyzed crash logs
- Checked memory patterns

**Results**:
```
Background Worker Status:
  Crashes (last 12 hours): 8
  Memory pattern: Steady growth from 200MB to 2GB over 2 hours
  Crash reason: OOMKilled
  Last crash: 02:00 UTC
```

#### Step 2: Analyze Memory Growth Pattern
```
What caused the memory to grow steadily?
```

**DevRelAgent Actions**:
- Correlated memory growth with task types
- Analyzed task execution patterns
- Checked for memory leaks in code

**Findings**:
```
Memory Growth Analysis:
- Tasks with memory growth: document_processing (85% of tasks)
- Memory per task: +50MB per document
- Issue: Document content not released after processing
- Code location: apps/workers/document_processor.py:145
```

#### Step 3: Identify Code Issue
```
Find the memory leak in the document processor
```

**DevRelAgent Actions**:
- Searched codebase for document processing
- Analyzed memory management
- Identified leak pattern

**Code Issue Found**:
```python
# apps/workers/document_processor.py:145
# BEFORE (Memory Leak)
def process_document(doc_id):
    content = load_document(doc_id)  # Loads 50MB
    results = analyze(content)
    # BUG: content never released
    # Large object stays in memory
    return results

# FIXED
def process_document(doc_id):
    with load_document(doc_id) as content:
        results = analyze(content)
    # content properly released
    return results
```

### Resolution

**Immediate Action**:
```
Generate a GitHub PR for the memory leak fix
```

**DevRelAgent Created**:
- Pull request with code fix
- Unit tests for memory management
- Performance regression tests

**Workaround**:
```
Configure more frequent worker restarts until fix is deployed
```

**DevRelAgent Generated**:
```yaml
Temporary Mitigation:
  Worker Restart Schedule:
    interval: 1 hour
    max_memory: 500MB
    action: restart

  Kubernetes ConfigMap:
    apiVersion: v1
    kind: ConfigMap
    data:
      WORKER_MAX_MEMORY: "500MB"
      WORKER_RESTART_INTERVAL: "3600"
```

### Lessons Learned

**What Went Well**:
- Pattern detection in memory growth
- Code-level issue identification
- Automated PR creation

**Areas for Improvement**:
- Memory leak testing in CI/CD
- Earlier alert thresholds
- Resource limit enforcement

### Preventive Measures Implemented

1. **Memory Profiling**: Regular profiling in CI/CD pipeline
2. **Resource Limits**: Strict memory limits with alerts
3. **Code Review Checklist**: Memory management review items
4. **Automated Testing**: Memory leak detection tests

---

## Summary of DevRelAgent Capabilities Demonstrated

### Incident Investigation
- ✅ Rapid error pattern analysis
- ✅ Root cause identification
- ✅ Correlation of metrics and logs
- ✅ Code-level issue detection

### Resolution Support
- ✅ Automated rollback plan generation
- ✅ Configuration fix recommendations
- ✅ Code fix creation (GitHub issues/PRs)
- ✅ Verification monitoring

### Prevention
- ✅ Detection of recurring patterns
- ✅ Recommendations for process improvements
- ✅ Configuration validation suggestions
- ✅ Testing and monitoring enhancements

### Communication
- ✅ Clear status updates
- ✅ Structured observation reports
- ✅ Actionable recommendations
- ✅ Audit trail for compliance

## Best Practices for Using DevRelAgent in Incidents

### Do's
1. **Start with clear questions**: Describe what you're observing
2. **Provide context**: Include time ranges and affected services
3. **Iterate**: Refine queries based on findings
4. **Verify**: Cross-check important findings
5. **Document**: Let DevRelAgent create incident reports

### Don'ts
1. **Don't rely solely on AI**: Verify critical findings manually
2. **Don't skip approvals**: Follow change management for fixes
3. **Don't ignore confidence scores**: Low confidence means uncertain results
4. **Don't skip monitoring**: Verify fixes are working
5. **Don't forget communication**: Keep stakeholders informed

## Integration with Incident Management

### Creating Incident Records

```
Create an incident record for the API error spike
```

**DevRelAgent Can**:
- Draft incident description
- List timeline of events
- Include root cause analysis
- Suggest resolution steps

### Post-Mortem Creation

```
Generate a post-mortem for the authentication outage
```

**DevRelAgent Can**:
- Summarize incident timeline
- Identify root causes
- Document impact
- Suggest preventive measures
- Create action items

### Continuous Improvement

```
What patterns do we see across recent incidents?
```

**DevRelAgent Can**:
- Analyze multiple incidents
- Identify common themes
- Suggest systemic improvements
- Track implementation of fixes

## Additional Resources

- [Incident Response Playbook](./incident-response.md)
- [Monitoring and Alerting](./monitoring.md)
- [Runbook Templates](./runbooks.md)
- [Communication Templates](./communication-templates.md)
