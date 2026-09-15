//! Object-level authorization for by-ID file and folder routes.
//!
//! The api-gateway validates the JWT and injects the caller's identity as
//! `X-User-ID`. Every handler that acts on a resource looked up by ID must
//! compare that identity against the resource's `owner_id` (and, where shared
//! access is intended, the share ACL) before touching it. Mismatches surface
//! as `*NotFound` so a caller cannot use the endpoints to enumerate other
//! users' resource IDs.

use actix_web::HttpRequest;
use uuid::Uuid;

use crate::errors::ServiceError;
use crate::metadata::MetadataClient;
use crate::models::{FileMetadata, FileShare, Folder, SharePermission};

/// What the caller is trying to do with a file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FileAccess {
    /// Read metadata, versions, or content. Owner or any share.
    Read,
    /// Modify content or name. Owner or an `editor` share.
    Write,
    /// Delete, trash, restore, move, or manage sharing. Owner only.
    Manage,
}

/// The authenticated caller, taken from the gateway-injected `X-User-ID`.
pub fn caller_id(req: &HttpRequest) -> Result<Uuid, ServiceError> {
    req.headers()
        .get("X-User-ID")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.trim().parse::<Uuid>().ok())
        .ok_or_else(|| ServiceError::Unauthorized("missing X-User-ID header".into()))
}

/// Pure policy decision: may `caller` perform `access` on `file` given the
/// file's share ACL?
pub fn file_access_allowed(
    file: &FileMetadata,
    shares: &[FileShare],
    caller: &Uuid,
    access: FileAccess,
) -> bool {
    if file.owner_id == *caller {
        return true;
    }
    let share = shares
        .iter()
        .find(|s| s.file_id == file.id && s.shared_with == *caller);
    match access {
        FileAccess::Read => share.is_some(),
        FileAccess::Write => matches!(
            share,
            Some(FileShare {
                permission: SharePermission::Editor,
                ..
            })
        ),
        FileAccess::Manage => false,
    }
}

/// Pure policy decision: only the owner may act on a folder.
pub fn folder_access_allowed(folder: &Folder, caller: &Uuid) -> bool {
    folder.owner_id == *caller
}

/// Load a file and verify `caller` may perform `access` on it.
///
/// Share lookups only happen when the caller is not the owner and shared
/// access is possible for the requested level.
pub async fn authorize_file(
    meta: &MetadataClient,
    file_id: &Uuid,
    caller: &Uuid,
    access: FileAccess,
) -> Result<FileMetadata, ServiceError> {
    let file = meta.get_file(file_id).await?;
    if file.owner_id == *caller {
        return Ok(file);
    }
    let shares = match access {
        FileAccess::Manage => Vec::new(),
        FileAccess::Read | FileAccess::Write => meta
            .find_existing_share(file_id, caller)
            .await?
            .into_iter()
            .collect(),
    };
    if file_access_allowed(&file, &shares, caller, access) {
        Ok(file)
    } else {
        tracing::warn!(
            file_id = %file_id,
            caller = %caller,
            access = ?access,
            "Denied access to file not owned by caller"
        );
        Err(ServiceError::FileNotFound(file_id.to_string()))
    }
}

/// Load a folder and verify `caller` owns it.
pub async fn authorize_folder(
    meta: &MetadataClient,
    folder_id: &Uuid,
    caller: &Uuid,
) -> Result<Folder, ServiceError> {
    let folder = meta.get_folder(folder_id).await?;
    if folder_access_allowed(&folder, caller) {
        Ok(folder)
    } else {
        tracing::warn!(
            folder_id = %folder_id,
            caller = %caller,
            "Denied access to folder not owned by caller"
        );
        Err(ServiceError::FolderNotFound(folder_id.to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use actix_web::test::TestRequest;
    use chrono::Utc;

    fn file(owner: Uuid) -> FileMetadata {
        let now = Utc::now();
        FileMetadata {
            id: Uuid::new_v4(),
            name: "report.pdf".into(),
            mime_type: "application/pdf".into(),
            size_bytes: 10,
            s3_key: "files/x/y".into(),
            folder_id: None,
            owner_id: owner,
            version: 1,
            is_trashed: false,
            created_at: now,
            updated_at: now,
        }
    }

    fn share(file: &FileMetadata, with: Uuid, permission: SharePermission) -> FileShare {
        FileShare {
            id: Uuid::new_v4(),
            file_id: file.id,
            shared_with: with,
            permission,
            shared_by: file.owner_id,
            created_at: Utc::now(),
        }
    }

    #[test]
    fn caller_id_requires_header() {
        let req = TestRequest::default().to_http_request();
        assert!(matches!(
            caller_id(&req),
            Err(ServiceError::Unauthorized(_))
        ));

        let req = TestRequest::default()
            .insert_header(("X-User-ID", "not-a-uuid"))
            .to_http_request();
        assert!(matches!(
            caller_id(&req),
            Err(ServiceError::Unauthorized(_))
        ));

        let id = Uuid::new_v4();
        let req = TestRequest::default()
            .insert_header(("X-User-ID", format!(" {id} ")))
            .to_http_request();
        assert_eq!(caller_id(&req).unwrap(), id);
    }

    #[test]
    fn owner_has_every_access() {
        let owner = Uuid::new_v4();
        let f = file(owner);
        for access in [FileAccess::Read, FileAccess::Write, FileAccess::Manage] {
            assert!(file_access_allowed(&f, &[], &owner, access));
        }
    }

    #[test]
    fn stranger_is_denied_every_access() {
        let f = file(Uuid::new_v4());
        let attacker = Uuid::new_v4();
        for access in [FileAccess::Read, FileAccess::Write, FileAccess::Manage] {
            assert!(!file_access_allowed(&f, &[], &attacker, access));
        }
    }

    #[test]
    fn share_on_another_file_does_not_grant_access() {
        let owner = Uuid::new_v4();
        let target = file(owner);
        let other = file(owner);
        let attacker = Uuid::new_v4();
        let shares = [share(&other, attacker, SharePermission::Editor)];
        assert!(!file_access_allowed(
            &target,
            &shares,
            &attacker,
            FileAccess::Read
        ));
    }

    #[test]
    fn viewer_share_grants_read_only() {
        let f = file(Uuid::new_v4());
        let viewer = Uuid::new_v4();
        let shares = [share(&f, viewer, SharePermission::Viewer)];
        assert!(file_access_allowed(&f, &shares, &viewer, FileAccess::Read));
        assert!(!file_access_allowed(
            &f,
            &shares,
            &viewer,
            FileAccess::Write
        ));
        assert!(!file_access_allowed(
            &f,
            &shares,
            &viewer,
            FileAccess::Manage
        ));
    }

    #[test]
    fn editor_share_grants_read_and_write_but_not_manage() {
        let f = file(Uuid::new_v4());
        let editor = Uuid::new_v4();
        let shares = [share(&f, editor, SharePermission::Editor)];
        assert!(file_access_allowed(&f, &shares, &editor, FileAccess::Read));
        assert!(file_access_allowed(&f, &shares, &editor, FileAccess::Write));
        assert!(!file_access_allowed(
            &f,
            &shares,
            &editor,
            FileAccess::Manage
        ));
    }

    #[test]
    fn folder_is_owner_only() {
        let owner = Uuid::new_v4();
        let now = Utc::now();
        let folder = Folder {
            id: Uuid::new_v4(),
            name: "docs".into(),
            parent_id: None,
            owner_id: owner,
            created_at: now,
            updated_at: now,
        };
        assert!(folder_access_allowed(&folder, &owner));
        assert!(!folder_access_allowed(&folder, &Uuid::new_v4()));
    }
}
