import { Routes } from '@angular/router';
import { AuthPage } from './pages/auth/auth';
import { DashboardPage } from './pages/dashboard/dashboard';
import { UploadPage } from './pages/upload/upload';
import { MeetingPage } from './pages/meeting/meeting'; //

export const routes: Routes =[
  { path: '', redirectTo: 'auth', pathMatch: 'full' },
  { path: 'auth', component: AuthPage },
  { path: 'dashboard', component: DashboardPage },
  { path: 'upload', component: UploadPage },
  { path: 'meeting/:id', component: MeetingPage }, //
  { path: '**', redirectTo: 'auth' },
];
