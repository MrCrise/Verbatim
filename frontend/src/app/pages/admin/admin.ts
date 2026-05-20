import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../api.service';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  templateUrl: './admin.html',
})
export class AdminPage implements OnInit {
  stats: any = null;
  users: any[] = [];
  searchQuery = '';
  isRoleEditMode = false;

  showAddUserModal = false;
  isCreatingUser = false;
  newUser = { name: '', email: '', password: '' };

  constructor(private api: ApiService, private router: Router) {}

  ngOnInit() {
    this.loadStats();
    this.loadUsers();
  }

  loadStats() {
    this.api.getAdminStats().subscribe({
      next: (res) => this.stats = res,
      error: () => this.router.navigate(['/dashboard'])
    });
  }

  loadUsers() {
    this.api.getAdminUsers().subscribe({
      next: (res) => this.users = res
    });
  }

  get filteredUsers() {
    if (!this.searchQuery.trim()) return this.users;
    const q = this.searchQuery.toLowerCase();
    return this.users.filter(u => u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q));
  }

  toggleRoleEditMode() {
    this.isRoleEditMode = !this.isRoleEditMode;
  }

  changeRole(user: any) {
    const newStatus = !user.is_admin;
    this.api.updateUserRole(user.id, newStatus).subscribe({
      next: () => user.is_admin = newStatus,
      error: (err) => alert(err.error?.detail || 'Ошибка доступа')
    });
  }

  openAddUserModal() {
    this.showAddUserModal = true;
    this.newUser = { name: '', email: '', password: '' };
  }

  closeAddUserModal() {
    this.showAddUserModal = false;
  }

  onCreateUser() {
    this.isCreatingUser = true;
    this.api.register({ email: this.newUser.email, password: this.newUser.password, full_name: this.newUser.name }).subscribe({
      next: () => {
        this.isCreatingUser = false;
        this.closeAddUserModal();
        this.loadUsers();
        this.loadStats();
      },
      error: (err) => {
        this.isCreatingUser = false;
        alert(err.error?.detail || 'Ошибка создания');
      }
    });
  }

  onLogout() {
    localStorage.removeItem('token');
    this.router.navigate(['/auth']);
  }

  formatDateOnly = (d?: string) => d ? new Date(d).toLocaleDateString('ru-RU') : '—';
  formatDateTime = (d?: string) => d ? new Date(d).toLocaleString('ru-RU', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'}) : '—';

  formatTimeComplex(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
  }

  formatBytes(bytes: number): string {
    const gb = bytes / (1024**3);
    return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1024**2).toFixed(1)} MB`;
  }
}
