//! Object-level authorization for user-scoped routes.
//!
//! The api-gateway validates the caller's JWT and injects the authenticated
//! user id as `X-User-ID`. Every per-id route resolves its resource by id, so
//! the caller must additionally be proven to own the resource (or to hold a
//! share grant on it) before the handler acts on it.

use actix_web::{dev::Payload, FromRequest, HttpRequest};
use futures_util::future::{ready, Ready};
use uuid::Uuid;

use crate::errors::ServiceError;
use crate::metadata::MetadataClient;
use crate::models::{FileMetadata, FileShare, Folder, SharePermission};

/// The authenticated caller, extracted from the `X-User-ID` header.
///
/// Used as a handler argument so that a user-scoped route cannot be written
/// without an identity: a missing or unparseable header fails the extractor
/// with 401 before the handler runs.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CallerId(pub Uuid);

impl CallerId {
    pub fn id(&self) -> Uuid {
        self.0
    }
}

pub fn caller_from_request(req: &HttpRequest) -> Result<CallerId, ServiceError> {
    req.headers()
        .get("X-User-ID")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.trim().parse::<Uuid>().ok())
        .map(CallerId)
        .ok_or_else(|| ServiceError::Unauthorized("missing or invalid X-User-ID header".into()))
}

impl FromRequest for CallerId {
    type Error = ServiceError;
    type Future = Ready<Result<Self, Self::Error>>;

    fn from_request(req: &HttpRequest, _payload: &mut Payload) -> Self::Future {
        ready(caller_from_request(req))
    }
}

/// The level of access a route needs on the resource it touches.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Access {
    /// Read the resource: owner, or any share grant.
    Read,
    /// Mutate the resource: owner, or an `editor` share grant.
    Write,
    /// Owner-only rights (hard delete, managing the share list).
    Own,
}

/// Decide whether `caller` may act on a file owned by `owner_id`, given the
/// caller's share grant on that file (if any).
pub fn decide_file_access(
    caller: CallerId,
    owner_id: Uuid,
    share: Option<&FileShare>,
    required: Access,
) -> Result<(), ServiceError> {
    if owner_id == caller.id() {
        return Ok(());
    }

    let granted = match (required, share.map(|s| &s.permission)) {
        (Access::Own, _) => false,
        (Access::Write, Some(SharePermission::Editor)) => true,
        (Access::Write, _) => false,
        (Access::Read, Some(_)) => true,
        (Access::Read, None) => false,
    };

    if granted {
        Ok(())
    } else {
        Err(ServiceError::Forbidden(
            "caller does not have access to this file".into(),
        ))
    }
}

/// Folders have no share table, so ownership is the only grant.
pub fn decide_folder_access(caller: CallerId, owner_id: Uuid) -> Result<(), ServiceError> {
    if owner_id == caller.id() {
        Ok(())
    } else {
        Err(ServiceError::Forbidden(
            "caller does not have access to this folder".into(),
        ))
    }
}

/// A moved file keeps its `owner_id`, and folders are owner-only, so a destination
/// folder must belong to the file's owner. Checking it against the caller instead
/// would stop an editor filing a shared file in the owner's folders while letting
/// them strand it in their own, where no listing can reach it.
pub fn decide_destination_folder(
    file_owner_id: Uuid,
    folder_owner_id: Uuid,
) -> Result<(), ServiceError> {
    if folder_owner_id == file_owner_id {
        Ok(())
    } else {
        Err(ServiceError::Forbidden(
            "destination folder does not belong to the file's owner".into(),
        ))
    }
}

/// Load a destination folder and check it against the file's owner.
pub async fn authorize_destination_folder(
    meta: &MetadataClient,
    folder_id: &Uuid,
    file_owner_id: Uuid,
) -> Result<Folder, ServiceError> {
    let folder = meta.get_folder(folder_id).await?;
    decide_destination_folder(file_owner_id, folder.owner_id)?;
    Ok(folder)
}

/// Load a file and authorize the caller against it at the required level.
pub async fn authorize_file(
    meta: &MetadataClient,
    file_id: &Uuid,
    caller: CallerId,
    required: Access,
) -> Result<FileMetadata, ServiceError> {
    let file = meta.get_file(file_id).await?;
    if file.owner_id == caller.id() {
        return Ok(file);
    }

    let share = match required {
        Access::Own => None,
        _ => meta.find_existing_share(file_id, &caller.id()).await?,
    };
    decide_file_access(caller, file.owner_id, share.as_ref(), required)?;
    Ok(file)
}

/// Load a folder and authorize the caller as its owner.
pub async fn authorize_folder(
    meta: &MetadataClient,
    folder_id: &Uuid,
    caller: CallerId,
) -> Result<Folder, ServiceError> {
    let folder = meta.get_folder(folder_id).await?;
    decide_folder_access(caller, folder.owner_id)?;
    Ok(folder)
}

#[cfg(test)]
mod tests {
    use super::*;
    use actix_web::http::StatusCode;
    use actix_web::test::TestRequest;
    use actix_web::ResponseError;
    use chrono::Utc;

    fn share(shared_with: Uuid, permission: SharePermission) -> FileShare {
        FileShare {
            id: Uuid::new_v4(),
            file_id: Uuid::new_v4(),
            shared_with,
            permission,
            shared_by: Uuid::new_v4(),
            created_at: Utc::now(),
        }
    }

    fn status_of(err: ServiceError) -> StatusCode {
        err.error_response().status()
    }

    #[test]
    fn caller_is_read_from_the_gateway_header() {
        let user = Uuid::new_v4();
        let req = TestRequest::default()
            .insert_header(("X-User-ID", user.to_string()))
            .to_http_request();
        assert_eq!(caller_from_request(&req).unwrap(), CallerId(user));
    }

    #[test]
    fn missing_or_invalid_caller_header_is_unauthorized() {
        let req = TestRequest::default().to_http_request();
        assert_eq!(
            status_of(caller_from_request(&req).unwrap_err()),
            StatusCode::UNAUTHORIZED
        );

        let req = TestRequest::default()
            .insert_header(("X-User-ID", "not-a-uuid"))
            .to_http_request();
        assert_eq!(
            status_of(caller_from_request(&req).unwrap_err()),
            StatusCode::UNAUTHORIZED
        );
    }

    #[test]
    fn owner_gets_every_level_of_file_access() {
        let owner = CallerId(Uuid::new_v4());
        for level in [Access::Read, Access::Write, Access::Own] {
            assert!(decide_file_access(owner, owner.id(), None, level).is_ok());
        }
    }

    #[test]
    fn stranger_is_forbidden_on_a_file() {
        let stranger = CallerId(Uuid::new_v4());
        for level in [Access::Read, Access::Write, Access::Own] {
            let err = decide_file_access(stranger, Uuid::new_v4(), None, level).unwrap_err();
            assert_eq!(status_of(err), StatusCode::FORBIDDEN);
        }
    }

    #[test]
    fn viewer_share_reads_but_does_not_mutate() {
        let caller = CallerId(Uuid::new_v4());
        let owner = Uuid::new_v4();
        let grant = share(caller.id(), SharePermission::Viewer);

        assert!(decide_file_access(caller, owner, Some(&grant), Access::Read).is_ok());
        for level in [Access::Write, Access::Own] {
            let err = decide_file_access(caller, owner, Some(&grant), level).unwrap_err();
            assert_eq!(status_of(err), StatusCode::FORBIDDEN);
        }
    }

    #[test]
    fn editor_share_mutates_but_never_owns() {
        let caller = CallerId(Uuid::new_v4());
        let owner = Uuid::new_v4();
        let grant = share(caller.id(), SharePermission::Editor);

        assert!(decide_file_access(caller, owner, Some(&grant), Access::Read).is_ok());
        assert!(decide_file_access(caller, owner, Some(&grant), Access::Write).is_ok());
        let err = decide_file_access(caller, owner, Some(&grant), Access::Own).unwrap_err();
        assert_eq!(status_of(err), StatusCode::FORBIDDEN);
    }

    #[test]
    fn folder_access_is_owner_only() {
        let owner = CallerId(Uuid::new_v4());
        assert!(decide_folder_access(owner, owner.id()).is_ok());

        let stranger = CallerId(Uuid::new_v4());
        let err = decide_folder_access(stranger, owner.id()).unwrap_err();
        assert_eq!(status_of(err), StatusCode::FORBIDDEN);
    }

    #[test]
    fn a_move_destination_belongs_to_the_file_owner_not_the_editor() {
        let owner = Uuid::new_v4();
        let editor = Uuid::new_v4();

        // An editor may file a shared file into the owner's folders,
        assert!(decide_destination_folder(owner, owner).is_ok());
        // but not into their own, which no listing could then navigate to.
        let err = decide_destination_folder(owner, editor).unwrap_err();
        assert_eq!(status_of(err), StatusCode::FORBIDDEN);
    }
}
