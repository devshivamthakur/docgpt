import { memo } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

const GuestRoute = memo(function GuestRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
});

export default GuestRoute;
