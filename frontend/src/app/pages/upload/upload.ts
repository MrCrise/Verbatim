import { Component, ViewChild, ElementRef, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { ApiService } from '../../api.service';

@Component({
  selector: 'app-upload',
  standalone: true,
  imports:[CommonModule, FormsModule, RouterModule],
  templateUrl: './upload.html',
})
export class UploadPage implements OnInit {
  isAdmin = false;
  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;

  userName = 'Загрузка...';
  selectedFile: File | null = null;
  meetingTitle = '';
  meetingDescription = '';
  uploading = false;

  constructor(private router: Router, private api: ApiService) {}

  ngOnInit() {
    this.api.getCurrentUser().subscribe({
      next: (user) => {
        this.userName = user.full_name || user.email;
        this.isAdmin = user.is_admin;
      },
      error: () => this.onLogout()
    });
  }

  onLogout() {
    localStorage.removeItem('token');
    this.router.navigate(['/auth']);
  }

  triggerFileInput() {
    this.fileInput.nativeElement.click();
  }

  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      this.selectedFile = file;
      if (!this.meetingTitle) {
        this.meetingTitle = file.name;
      }
    }
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      this.selectedFile = files[0];
      if (!this.meetingTitle) {
        this.meetingTitle = files[0].name;
      }
    }
  }

  startUpload() {
    if (!this.selectedFile) return;

    this.uploading = true;
    this.api.uploadFile(this.selectedFile, this.meetingTitle).subscribe({
      next: () => {
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        console.error('Ошибка:', err);
        alert('Ошибка при загрузке файла');
        this.uploading = false;
      }
    });
  }
}
