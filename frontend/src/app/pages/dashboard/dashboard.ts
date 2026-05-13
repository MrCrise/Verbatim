import { Component, OnInit, NgZone, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { ApiService, MeetingResponse } from '../../api.service';
import { DurationPipe } from '../../pipes/duration.pipe';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterModule, DurationPipe],
  templateUrl: './dashboard.html',
})

export class DashboardPage implements OnInit, OnDestroy {
  userName = 'Загрузка...';
  isAdmin = false;
  meetings: MeetingResponse[] =[];
  private pollingTimer: any;

  constructor(
    private router: Router,
    private api: ApiService,
    private zone: NgZone,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit() {
    this.loadUser();
    this.loadMeetings();
    this.api.getCurrentUser().subscribe(user => {
      this.isAdmin = user.is_admin;
      this.userName = user.full_name || user.email;
    });
  }

  loadUser() {
    this.api.getCurrentUser().subscribe({
      next: (user) => {
        this.userName = user.full_name || user.email;
        this.isAdmin = user.is_admin;
        this.cdr.detectChanges();
      },
      error: () => this.onLogout()
    });
  }

  loadMeetings() {
    this.api.getMeetings().subscribe({
      next: (res) => {
        let hasProcessing = false;
        if (Array.isArray(res)) {
          this.meetings = res;
          // Проверяем, есть ли файлы в процессе, чтобы запустить автообновление
          hasProcessing = res.some(m => m.status === 'PROCESSING' || m.status === 'UPLOADED');
        }
        this.cdr.detectChanges();

        if (hasProcessing) {
          this.startGlobalPolling();
        } else {
          this.stopPolling();
        }
      },
      error: (err) => {
        if (err.status === 401) this.onLogout();
      }
    });
  }

  startGlobalPolling() {
    if (this.pollingTimer) return;

    this.zone.runOutsideAngular(() => {
      this.pollingTimer = setInterval(() => {
        this.api.getMeetings().subscribe((res) => {
          this.zone.run(() => {
            let hasProcessing = false;
            if (Array.isArray(res)) {
              this.meetings = res;
              hasProcessing = res.some(m => m.status === 'PROCESSING' || m.status === 'UPLOADED');
            }
            this.cdr.detectChanges();
            if (!hasProcessing) this.stopPolling();
          });
        });
      }, 4000); // Опрашиваем каждые 4 секунды
    });
  }

  stopPolling() {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
  }

  onLogout() {
    localStorage.removeItem('token');
    this.router.navigate(['/auth']);
  }

  formatDate(dateStr?: string) {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleString('ru-RU', {
      day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  }

  ngOnDestroy() {
    this.stopPolling();
  }
}
