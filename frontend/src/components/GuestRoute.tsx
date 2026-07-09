import { Navigate } from 'react-router-dom';

function GuestRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('docgpt-token');
  if (token) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

export default GuestRoute;
