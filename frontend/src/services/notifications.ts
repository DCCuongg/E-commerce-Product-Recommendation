import { DEMO_MODE } from './auth';
export type Notice={id:number;type:'order'|'account'|'offer';title:string;body:string;time:string;unread:boolean;orderId?:number};
const samples:Notice[]=[
{id:1,type:'order',title:'Your order has been confirmed',body:'Your order #10428 has been confirmed. You can check its products, current status, and order total from the My Purchases section. We will show delivery tracking when the backend makes it available.',time:'Nov 18, 2026',unread:true,orderId:10428},
{id:2,type:'offer',title:'Explore your next favorite instrument',body:'Your account is ready to help you discover equipment, instruments, and accessories. Product recommendations will be available when the store homepage is implemented.',time:'Nov 16, 2026',unread:true},
{id:3,type:'order',title:'Your purchase has been delivered',body:'Order #10396 has been marked as delivered. Visit your purchase history to see the items and their prices. Shipping proof is not available in the current order backend.',time:'Nov 4, 2026',unread:false,orderId:10396},
{id:4,type:'account',title:'Welcome to Soundwave',body:'Your account was successfully created. You can manage your username and email, review your purchases, and read notifications from the account center.',time:'Oct 29, 2026',unread:false},
];
export const notices=():Notice[]=>DEMO_MODE?samples:[];
export function readNoticeKey(userId:string){return `soundwave-notice-read-${userId}`;}
export function isNoticeRead(notice:Notice,userId:string){try{const marked=JSON.parse(localStorage.getItem(readNoticeKey(userId))||'[]') as number[];return !notice.unread||marked.includes(notice.id)}catch{return !notice.unread}}
export function markNoticeRead(ids:number[],userId:string){try{const key=readNoticeKey(userId);const prior=JSON.parse(localStorage.getItem(key)||'[]') as number[];localStorage.setItem(key,JSON.stringify([...new Set([...prior,...ids])]));}catch{/* storage unavailable */}}
