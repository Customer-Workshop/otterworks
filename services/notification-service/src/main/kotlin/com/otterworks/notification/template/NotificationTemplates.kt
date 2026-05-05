package com.otterworks.notification.template

import com.otterworks.notification.model.SqsNotificationMessage

data class RenderedNotification(
    val title: String,
    val message: String,
    val emailSubject: String,
    val emailBody: String,
)

object NotificationTemplates {

    private data class Template(
        val titleTemplate: String,
        val messageTemplate: String,
        val emailSubjectTemplate: String,
        val emailBodyTemplate: String,
    )

    private val templates = mapOf(
        "file_shared" to Template(
            titleTemplate = "File Shared With You",
            messageTemplate = "A file has been shared with you by user {{actorId}}.",
            emailSubjectTemplate = "OtterWorks: A file has been shared with you",
            emailBodyTemplate = """
                <html>
                <body>
                    <h2>File Shared</h2>
                    <p>A file (ID: {{fileId}}) has been shared with you by user {{actorId}}.</p>
                    <p>Log in to OtterWorks to view the file.</p>
                    <br/>
                    <p style="color: #888;">— OtterWorks Notification Service</p>
                </body>
                </html>
            """.trimIndent(),
        ),
        "comment_added" to Template(
            titleTemplate = "New Comment",
            messageTemplate = "A new comment was added by user {{actorId}} on document {{documentId}}.",
            emailSubjectTemplate = "OtterWorks: New comment on your document",
            emailBodyTemplate = """
                <html>
                <body>
                    <h2>New Comment</h2>
                    <p>User {{actorId}} added a comment on document {{documentId}}.</p>
                    <p>Log in to OtterWorks to view the comment.</p>
                    <br/>
                    <p style="color: #888;">— OtterWorks Notification Service</p>
                </body>
                </html>
            """.trimIndent(),
        ),
        "document_edited" to Template(
            titleTemplate = "Document Edited",
            messageTemplate = "Document {{documentId}} was edited by user {{actorId}}.",
            emailSubjectTemplate = "OtterWorks: A document you follow was edited",
            emailBodyTemplate = """
                <html>
                <body>
                    <h2>Document Edited</h2>
                    <p>Document {{documentId}} was edited by user {{actorId}}.</p>
                    <p>Log in to OtterWorks to view the changes.</p>
                    <br/>
                    <p style="color: #888;">— OtterWorks Notification Service</p>
                </body>
                </html>
            """.trimIndent(),
        ),
        "user_mentioned" to Template(
            titleTemplate = "You Were Mentioned",
            messageTemplate = "You were mentioned by user {{actorId}} in document {{documentId}}.",
            emailSubjectTemplate = "OtterWorks: You were mentioned in a document",
            emailBodyTemplate = """
                <html>
                <body>
                    <h2>You Were Mentioned</h2>
                    <p>User {{actorId}} mentioned you in document {{documentId}}.</p>
                    <p>Log in to OtterWorks to see the context.</p>
                    <br/>
                    <p style="color: #888;">— OtterWorks Notification Service</p>
                </body>
                </html>
            """.trimIndent(),
        ),
        "vulnerability_detected" to Template(
            titleTemplate = "[{{severity}}] Security Vulnerability Detected",
            messageTemplate = "{{severity}} vulnerability {{cveId}} found in {{service}}: {{packageName}} (fix: {{fixedVersion}}).",
            emailSubjectTemplate = "OtterWorks Security: {{severity}} vulnerability in {{service}}",
            emailBodyTemplate = """
                <html>
                <body>
                    <h2 style="color: #d32f2f;">Security Vulnerability Detected</h2>
                    <table>
                        <tr><td><strong>Severity:</strong></td><td>{{severity}}</td></tr>
                        <tr><td><strong>CVE:</strong></td><td>{{cveId}}</td></tr>
                        <tr><td><strong>Service:</strong></td><td>{{service}}</td></tr>
                        <tr><td><strong>Package:</strong></td><td>{{packageName}}</td></tr>
                        <tr><td><strong>Fixed Version:</strong></td><td>{{fixedVersion}}</td></tr>
                    </table>
                    <p>Automated remediation has been initiated via Devin.</p>
                    <br/>
                    <p style="color: #888;">— OtterWorks Security Pipeline</p>
                </body>
                </html>
            """.trimIndent(),
        ),
        "remediation_completed" to Template(
            titleTemplate = "Security Remediation Complete",
            messageTemplate = "Automated remediation for {{service}} completed. PR: {{prUrl}}.",
            emailSubjectTemplate = "OtterWorks Security: Remediation PR created for {{service}}",
            emailBodyTemplate = """
                <html>
                <body>
                    <h2 style="color: #2e7d32;">Security Remediation Complete</h2>
                    <p>Automated remediation for <strong>{{service}}</strong> has been completed.</p>
                    <p><a href="{{prUrl}}">Review the remediation PR</a></p>
                    <br/>
                    <p style="color: #888;">— OtterWorks Security Pipeline</p>
                </body>
                </html>
            """.trimIndent(),
        ),
    )

    fun render(event: SqsNotificationMessage): RenderedNotification {
        val template = templates[event.eventType] ?: return RenderedNotification(
            title = "Notification",
            message = "You have a new notification.",
            emailSubject = "OtterWorks: New notification",
            emailBody = "<html><body><p>You have a new notification.</p></body></html>",
        )

        val variables = mapOf(
            "actorId" to (event.actorId.ifEmpty { event.ownerId }),
            "fileId" to event.fileId,
            "documentId" to event.documentId,
            "commentId" to event.commentId,
            "userId" to event.userId,
            "scanId" to event.scanId,
            "severity" to event.severity,
            "cveId" to event.cveId,
            "service" to event.service,
            "packageName" to event.packageName,
            "fixedVersion" to event.fixedVersion,
            "devinSessionId" to event.devinSessionId,
            "prUrl" to event.prUrl,
        )

        return RenderedNotification(
            title = replaceVariables(template.titleTemplate, variables),
            message = replaceVariables(template.messageTemplate, variables),
            emailSubject = replaceVariables(template.emailSubjectTemplate, variables),
            emailBody = replaceVariables(template.emailBodyTemplate, variables),
        )
    }

    private fun replaceVariables(template: String, variables: Map<String, String>): String {
        var result = template
        for ((key, value) in variables) {
            result = result.replace("{{$key}}", value)
        }
        return result
    }
}
