import {
  Component,
  ElementRef,
  ViewChild,
  AfterViewInit
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService } from '../services/chat.service';
import { trigger, transition, style, animate } from '@angular/animations';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule  
  ],
  animations: [
    trigger('chatSlide', [
      transition(':enter', [
        style({ transform: 'translateY(100%)', opacity: 0 }),
        animate('300ms ease-out', style({ transform: 'translateY(0)', opacity: 1 }))
      ]),
      transition(':leave', [
        animate('300ms ease-in', style({ transform: 'translateY(100%)', opacity: 0 }))
      ])
    ])
  ],
  templateUrl: './chat.component.html',
})
export class ChatComponent implements AfterViewInit {
  prompt = '';
  tokens = 0;
  isChatOpen = false;
  messages: { user: 'User' | 'AI'; text: string }[] = [];

  @ViewChild('messageContainer') messageContainer!: ElementRef;

  constructor(private chatService: ChatService) {
    console.log('ChatComponent loaded');
  }

  ngAfterViewInit() {
    this.scrollToBottom();
  }

  toggleChat() {
    console.log('Chat toggle clicked');
    this.isChatOpen = !this.isChatOpen;
    setTimeout(() => this.scrollToBottom(), 100);
  }

  askQuestion() {
    const trimmed = this.prompt.trim();
    if (!trimmed) return;

    this.messages.push({ user: 'User', text: trimmed });
    this.prompt = '';
    this.scrollToBottom();

    this.chatService.sendPrompt(trimmed).subscribe({
      next: (res) => {
        this.messages.push({ user: 'AI', text: res.response });
        this.tokens += res.tokens;
        this.scrollToBottom();
      },
      error: () => {
        this.messages.push({ user: 'AI', text: '❌ Failed to respond' });
        this.scrollToBottom();
      }
    });
  }

  onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.askQuestion();
    }
  }

  scrollToBottom() {
    setTimeout(() => {
      const el = this.messageContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 0);
  }
}
