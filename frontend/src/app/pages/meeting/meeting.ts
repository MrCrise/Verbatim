import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ApiService, MeetingResponse } from '../../api.service';

@Component({
  selector: 'app-meeting',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './meeting.html',
})
export class MeetingPage implements OnInit, OnDestroy {
  // ДОБАВЛЕНО: Ссылка на HTML5 аудио-плеер
  @ViewChild('audioPlayer') audioPlayer!: ElementRef<HTMLAudioElement>;

  meetingId: string = '';
  meeting: MeetingResponse | null = null;
  userName = 'Системный Пользователь';

  audioUrl: string | null = null;
  isDownloading = false;

  speakersMap: Record<string, string> = {};
  editingSpeaker: string | null = null;
  activeSpeakerFilter: string | null = null;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private api: ApiService
  ) {}

  ngOnInit() {
    this.meetingId = this.route.snapshot.paramMap.get('id') || '';
    if (this.meetingId) {
      this.loadMeeting();
      this.loadAudioForPlayer();
    }
  }

  loadMeeting() {
    this.api.getMeeting(this.meetingId).subscribe({
      next: (res) => {
        this.meeting = res;
        if (this.meeting.transcript_data?.speakers) {
          this.meeting.transcript_data.speakers.forEach(spk => {
            this.speakersMap[spk] = spk;
          });
        }
      },
      error: () => this.router.navigate(['/dashboard'])
    });
  }

  loadAudioForPlayer() {
    this.api.streamAudio(this.meetingId).subscribe({
      next: (blob) => {
        this.audioUrl = URL.createObjectURL(blob);
      }
    });
  }

  // --- МАГИЯ: Клик на таймкод и проигрывание ---
  playFrom(timeInSeconds: number) {
    if (this.audioPlayer && this.audioPlayer.nativeElement) {
      const player = this.audioPlayer.nativeElement;
      player.currentTime = timeInSeconds;
      player.play();
    }
  }

  formatDate(dateStr?: string) {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  onLogout() {
    localStorage.removeItem('token');
    this.router.navigate(['/auth']);
  }

  onDownload() {
    if (this.isDownloading) return;
    this.isDownloading = true;
    this.api.downloadAudio(this.meetingId).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = this.meeting?.title || 'audio.wav';
        a.click();
        window.URL.revokeObjectURL(url);
        this.isDownloading = false;
      },
      error: () => {
        alert('Ошибка при скачивании файла');
        this.isDownloading = false;
      }
    });
  }

  startRenaming(speakerId: string, event: Event) {
    event.stopPropagation();
    this.editingSpeaker = speakerId;
  }

  saveRenaming() {
    this.editingSpeaker = null;
  }

  setFilter(speakerId: string | null) {
    this.activeSpeakerFilter = speakerId;
  }

  getFilteredSegments() {
    if (!this.meeting?.transcript_data?.segments) return[];
    if (!this.activeSpeakerFilter) return this.meeting.transcript_data.segments;
    return this.meeting.transcript_data.segments.filter(
      seg => seg.speaker === this.activeSpeakerFilter
    );
  }

  ngOnDestroy() {
    if (this.audioUrl) {
      URL.revokeObjectURL(this.audioUrl);
    }
  }
}
