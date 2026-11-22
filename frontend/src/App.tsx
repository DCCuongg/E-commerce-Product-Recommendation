import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import type { Location } from 'react-router-dom';
import { ProtectedRoute } from './components/UI';
import DetailModal from './components/DetailModal';
import Home from './pages/Home';
import Catalog from './pages/Catalog';
import ProductDetails from './pages/ProductDetails';
import Cart from './pages/Cart';
import Checkout from './pages/Checkout';
import AccountLayout from './components/AccountLayout';
import SignIn from './pages/SignIn';
import SignUp from './pages/SignUp';
import Profile from './pages/Profile';
import EditProfile from './pages/EditProfile';
import Purchases from './pages/Purchases';
import Notifications from './pages/Notifications';
import OrderDetail from './pages/OrderDetail';
import NotificationDetail from './pages/NotificationDetail';

export default function App() {
  const location = useLocation();
  const state = location.state as { backgroundLocation?: Location } | null;
  const background = state?.backgroundLocation;
  return (
    <>
      <Routes location={background || location}>
        <Route path="/" element={<Home />} />
        <Route path="/shop" element={<Catalog />} />
        <Route path="/products/:productId" element={<ProductDetails />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/cart" element={<Cart />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/profile" element={<AccountLayout />}>
            <Route index element={<Profile />} />
            <Route path="edit" element={<EditProfile />} />
            <Route path="purchases" element={<Purchases />} />
            <Route path="notifications" element={<Notifications />} />
            <Route path="purchases/:orderId" element={<OrderDetail />} />
            <Route path="notifications/:notificationId" element={<NotificationDetail />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {background && (
        <Routes>
          <Route path="/profile/purchases/:orderId" element={<DetailModal title="Order details" wide><OrderDetail /></DetailModal>} />
          <Route path="/profile/notifications/:notificationId" element={<DetailModal title="Notification details"><NotificationDetail /></DetailModal>} />
        </Routes>
      )}
    </>
  );
}