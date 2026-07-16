import { memo } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

const ProtectedRoute = memo(function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
});

export default ProtectedRoute;
