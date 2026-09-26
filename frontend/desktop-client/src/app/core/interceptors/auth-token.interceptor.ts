import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { SessionService } from '../services/session.service';

/** Attaches `Authorization: Bearer <token>` to every non-auth request (port of ApplyAuth). */
export const authTokenInterceptor: HttpInterceptorFn = (request, next) => {
  const session = inject(SessionService);
  const token = session.accessToken();

  if (!token || request.url.includes('/auth/')) {
    return next(request);
  }

  return next(
    request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
  );
};
