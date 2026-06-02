# ServiceNow Configuration Guide

Step-by-step instructions for configuring ServiceNow to send incident webhooks to the Devin AI automated remediation system.

> **Instance used in this guide:** `koniaggovernmentservicesllcdemo1.service-now.com`
> Replace with your own instance URL if different.

---

## Prerequisites

- ServiceNow admin access
- The webhook Lambda stack deployed (see [README.md](./README.md) — run `deploy.sh`)
- The API Gateway webhook URL from the deploy output

---

## Step 1: Create the Outbound REST Message

This saves a reusable HTTP call template that the Business Rule will invoke.

1. Open the REST Message list:
   **https://koniaggovernmentservicesllcdemo1.service-now.com/sys_rest_message_list.do**

2. Click **New**

3. Fill in:
   | Field | Value |
   |-------|-------|
   | **Name** | `Devin Bug Remediation` |
   | **Endpoint** | `https://<your-api-gateway-id>.execute-api.us-east-1.amazonaws.com/prod/api/v1/admin/servicenow/ingest` |
   | **Authentication type** | `No authentication` |

4. Click **Submit**

5. Re-open the record. Scroll down to **HTTP Methods** and click **New**:
   | Field | Value |
   |-------|-------|
   | **Name** | `POST_Incident` |
   | **HTTP method** | `POST` |

6. Under **HTTP Request**, add these **HTTP Headers** (click the lock icon first if needed):
   | Name | Value |
   |------|-------|
   | `Content-Type` | `application/json` |
   | `X-ServiceNow-Secret` | *(the shared secret you used in deploy.sh)* |

7. Set the **Content** (request body):
   ```json
   {
     "source": "servicenow",
     "incident": {
       "sys_id": "${sys_id}",
       "number": "${number}",
       "short_description": "${short_description}",
       "description": "${description}",
       "priority": "${priority}",
       "category": "${category}",
       "subcategory": "${subcategory}",
       "assignment_group": "${assignment_group}",
       "assigned_to": "${assigned_to}",
       "caller_id": "${caller_id}",
       "cmdb_ci": "${cmdb_ci}",
       "state": "${state}",
       "sys_created_on": "${sys_created_on}"
     }
   }
   ```

8. Scroll down to **Variable Substitutions**. Add each variable with a test value:

   | Name | Test value |
   |------|-----------|
   | `sys_id` | `abc123` |
   | `number` | `INC0010001` |
   | `short_description` | `Test incident` |
   | `description` | `Test description` |
   | `priority` | `1` |
   | `category` | `Software` |
   | `subcategory` | `Operating System` |
   | `assignment_group` | `Service Desk` |
   | `assigned_to` | `admin` |
   | `caller_id` | `admin` |
   | `cmdb_ci` | `file-service` |
   | `state` | `1` |
   | `sys_created_on` | `2026-01-01 00:00:00` |

9. Click **Submit**

---

## Step 2: Create the Business Rule

This automatically fires the webhook when a qualifying incident is created.

1. Open the Business Rules list:
   **https://koniaggovernmentservicesllcdemo1.service-now.com/sys_script_list.do**

2. Click **New**

3. Fill in the **When to run** section:
   | Field | Value |
   |-------|-------|
   | **Name** | `Trigger Devin Remediation` |
   | **Table** | `Incident [incident]` |
   | **Advanced** | ✅ Check this box |
   | **When** | `after` |
   | **Insert** | ✅ |
   | **Update** | ❌ (uncheck unless you want updates too) |

4. Set **Filter Conditions** (click "Add filter condition"):
   - `Category` → `is` → `Software`
   - AND `Priority` → `is one of` → `1 - Critical`, `2 - High`

   > **Tip:** For the demo, you can use just `1 - Critical` to make it easy to test selectively.

5. Switch to the **Advanced** script tab and paste:

   ```javascript
   (function executeRule(current, previous) {
       try {
           var r = new sn_ws.RESTMessageV2('Devin Bug Remediation', 'POST_Incident');
           r.setStringParameterNoEscape('sys_id', current.sys_id.toString());
           r.setStringParameterNoEscape('number', current.number.toString());
           r.setStringParameterNoEscape('short_description', current.short_description.toString());
           r.setStringParameterNoEscape('description', current.description.toString());
           r.setStringParameterNoEscape('priority', current.priority.toString());
           r.setStringParameterNoEscape('category', current.category.toString());
           r.setStringParameterNoEscape('subcategory', current.subcategory.toString());
           r.setStringParameterNoEscape('assignment_group', current.assignment_group.getDisplayValue());
           r.setStringParameterNoEscape('assigned_to', current.assigned_to.getDisplayValue());
           r.setStringParameterNoEscape('caller_id', current.caller_id.getDisplayValue());
           r.setStringParameterNoEscape('cmdb_ci', current.cmdb_ci.getDisplayValue());
           r.setStringParameterNoEscape('state', current.state.toString());
           r.setStringParameterNoEscape('sys_created_on', current.sys_created_on.toString());
           var response = r.execute();
           gs.info('Devin webhook response: ' + response.getStatusCode());
       } catch (ex) {
           gs.error('Devin webhook failed: ' + ex.message);
       }
   })(current, previous);
   ```

6. Click **Submit**

---

## Step 3: Configure OAuth 2.0 for API Callbacks

The webhook uses OAuth 2.0 Client Credentials to authenticate when posting work notes and resolving incidents back in ServiceNow.

### 3a. Enable the Client Credentials grant type (required)

The `client_credentials` grant type is **disabled by default** on ServiceNow. You must enable it via a system property before OAuth will work:

1. Navigate to **System Properties**:
   **https://koniaggovernmentservicesllcdemo1.service-now.com/sys_properties_list.do**

2. Click **New** and create the following property:
   | Field | Value |
   |-------|-------|
   | **Name** | `glide.oauth.inbound.client.credential.grant_type.enabled` |
   | **Type** | `true_false` |
   | **Value** | `true` |

3. Click **Submit**

> **Tip:** You can also verify this via the Machine Identity Console (**System OAuth > Application Registry** → banner link to **New Inbound Integration Experience**). If the property is missing, a yellow warning banner will appear on client-credential app records.

### 3b. Create an OAuth Application Registry entry

1. Navigate to **System OAuth > Application Registry**:
   **https://koniaggovernmentservicesllcdemo1.service-now.com/oauth_entity_list.do**

2. Click **New** → select **"Create an OAuth API endpoint for external clients"**

3. Fill in:
   | Field | Value |
   |-------|-------|
   | **Name** | `Devin AI Integration` |
   | **Client ID** | *(auto-generated — copy this value)* |
   | **Client Secret** | *(auto-generated — copy this value)* |
   | **Token Lifespan** | `1800` (30 minutes, default) |
   | **Refresh Token Lifespan** | `0` (not used for client credentials) |

4. Configure the OAuth app for client credentials:
   | Field | Value |
   |-------|-------|
   | **Default Grant Type** | `Client Credentials` |
   | **Client Type** | `Integration as a Service` |
   | **Scope Restriction** | `Broadly scoped` (or configure specific auth scopes) |

5. Set the **User** field to the service account that should be associated with tokens (see Step 3c).

6. Click **Submit**

7. Note down the **Client ID** and **Client Secret** — you will need them for the Lambda deployment.

### 3c. Create a dedicated service account (recommended)

1. Navigate to **User Administration > Users**

2. Click **New** and create a non-interactive service account:
   | Field | Value |
   |-------|-------|
   | **User ID** | `svc_devin_integration` |
   | **First name** | `Devin` |
   | **Last name** | `Integration (Service Account)` |
   | **Active** | ✅ |
   | **Web service access only** | ✅ |

3. Assign the minimum required roles:
   - `itil` — allows reading/writing incident records
   - Or create a custom role scoped to the `incident` table with read/write permissions for `work_notes`, `state`, `close_code`, and `close_notes` fields.

### 3c. Set environment variables for deployment

When deploying the Lambda, provide these environment variables (via `deploy.sh` flags or environment):

```bash
export SERVICENOW_INSTANCE_URL="https://koniaggovernmentservicesllcdemo1.service-now.com"
export SERVICENOW_CLIENT_ID="<your-client-id-from-step-3a>"
export SERVICENOW_CLIENT_SECRET="<your-client-secret-from-step-3a>"
```

Or pass them as deploy flags:

```bash
./deploy.sh \
  --snow-instance "https://koniaggovernmentservicesllcdemo1.service-now.com" \
  --snow-client-id "<your-client-id>" \
  --snow-client-secret "<your-client-secret>"
```

> **Note:** The previous `SERVICENOW_USERNAME` / `SERVICENOW_PASSWORD` environment variables
> are no longer used. The integration now authenticates via OAuth 2.0 Client Credentials,
> posting to `/oauth_token.do` to obtain a Bearer token before each API call batch.

---

## Step 4: (Optional) Create a Scripted REST API for Callbacks

This lets the webhook post remediation results *back* to ServiceNow.

1. Open: **https://koniaggovernmentservicesllcdemo1.service-now.com/sys_ws_definition_list.do**

2. Click **New**:
   | Field | Value |
   |-------|-------|
   | **Name** | `Devin Callback` |
   | **API ID** | `devin_callback` |

3. Submit, then open the record and add a **Resource**:
   | Field | Value |
   |-------|-------|
   | **Name** | `Update Incident` |
   | **HTTP method** | `POST` |
   | **Relative path** | `/update_incident` |

4. Script:
   ```javascript
   (function process(request, response) {
       var body = request.body.data;
       var sysId = body.sys_id;
       var gr = new GlideRecord('incident');
       if (gr.get(sysId)) {
           gr.work_notes = 'Devin AI Remediation Update:\n'
               + 'Status: ' + body.status + '\n'
               + 'PR: ' + (body.pr_url || 'N/A') + '\n'
               + 'Session: ' + (body.session_url || 'N/A') + '\n'
               + 'Summary: ' + (body.summary || '');
           if (body.status === 'resolved') {
               gr.state = 6;
               gr.close_notes = 'Auto-resolved by Devin AI. PR: ' + (body.pr_url || 'N/A');
           }
           gr.update();
           response.setStatus(200);
           response.setBody({result: 'updated'});
       } else {
           response.setStatus(404);
           response.setBody({error: 'Incident not found'});
       }
   })(request, response);
   ```

5. Click **Submit**

---

## Step 5: Test End-to-End

1. Go to the incident list:
   **https://koniaggovernmentservicesllcdemo1.service-now.com/now/sow/list/incident**

2. Click **New** to create a new incident

3. Fill in:
   | Field | Value |
   |-------|-------|
   | **Caller** | Pick any user |
   | **Category** | `Software` |
   | **Impact** | `1 - High` |
   | **Urgency** | `1 - High` |
   | **Short description** | `File upload returns 500 error in file-service` |
   | **Description** | `Users report intermittent 500 errors when uploading files larger than 10MB` |

4. Click **Save**

5. The Business Rule fires → webhook receives the incident → Devin session starts

6. Check the Lambda logs:
   ```bash
   aws logs tail /aws/lambda/otterworks-servicenow-webhook-webhook --follow --region us-east-1
   ```

7. The incident's **Work Notes** should show a note from Devin with the session URL (if ServiceNow callback credentials were configured).

---

## Troubleshooting

### Business Rule not firing
- Check **System Logs → System Log → All**: filter by `Devin webhook`
- Verify the filter conditions match your incident (Category=Software, Priority=1)

### REST Message errors
- Open the REST Message → HTTP Method → click **Test**
- Check the response code and body

### Lambda errors
```bash
aws logs tail /aws/lambda/otterworks-servicenow-webhook-webhook --follow --region us-east-1
```

### Redeploy after code changes
```bash
cd integrations/servicenow && ./deploy.sh
```
