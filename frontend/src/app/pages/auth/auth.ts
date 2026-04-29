import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../../api.service';

@Component({
  selector: 'app-auth',
  standalone: true,
  imports:[CommonModule, FormsModule],
  templateUrl: './auth.html',
})
export class AuthPage {
  mode = signal<'login' | 'register'>('login');

  loginEmail = '';
  loginPassword = '';

  registerName = '';
  registerEmail = '';
  registerPassword = '';
  registerConfirmPassword = '';

  constructor(private api: ApiService, private router: Router) {}

  setMode(m: 'login' | 'register') {
    this.mode.set(m);
  }

  onLogin() {
    const body = new FormData();
    body.append('username', this.loginEmail);
    body.append('password', this.loginPassword);

    this.api.login(body).subscribe({
      next: () => this.router.navigate(['/dashboard']),
      error: (err) => alert('Ошибка входа: ' + (err.error?.detail || 'Сервер недоступен'))
    });
  }

  onRegister() {
    const data = {
      email: this.registerEmail,
      password: this.registerPassword,
      full_name: this.registerName
    };

    this.api.register(data).subscribe({
      next: () => {
        alert('Успешная регистрация! Теперь войдите.');
        this.setMode('login');
      },
      error: (err) => alert('Ошибка регистрации: ' + (err.error?.detail || 'Сервер недоступен'))
    });
  }
}
