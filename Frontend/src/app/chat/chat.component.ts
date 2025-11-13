import {
  Component,
  ElementRef,
  ViewChild,
  AfterViewInit,
  OnInit
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService } from '../services/chat.service';
import { trigger, transition, style, animate } from '@angular/animations';
import { LucideAngularModule, MessageCircle, X, Send, Trash2, Sparkles } from 'lucide-angular';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, LucideAngularModule],
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
  styleUrl: './chat.component.css',
  templateUrl: './chat.component.html',
})
export class ChatComponent implements OnInit, AfterViewInit {
  prompt = '';
  tokens = 0;
  isChatOpen = false;
  hasWelcomed = false;

  messages: { user: 'User' | 'AI'; text: string; timestamp?: Date }[] = [];

  @ViewChild('messageContainer') messageContainer!: ElementRef;

  // Lucide icons
  readonly MessageCircle = MessageCircle;
  readonly X = X;
  readonly Send = Send;
  readonly Trash2 = Trash2;
  readonly Sparkles = Sparkles;

  constructor(private chatService: ChatService) {}

  ngOnInit() {
    const saved = localStorage.getItem('chatHistory');
    if (saved) this.messages = JSON.parse(saved);

    this.hasWelcomed = !!saved && this.messages.length > 0;
  }

  ngAfterViewInit() {
    this.scrollToBottom();
  }

  saveChatHistory() {
    localStorage.setItem('chatHistory', JSON.stringify(this.messages));
  }

  clearChat() {
    this.messages = [];
    localStorage.removeItem('chatHistory');
  }

  toggleChat() {
    this.isChatOpen = !this.isChatOpen;

    const isFirstInteraction = !this.hasWelcomed && this.messages.length === 0;

    if (this.isChatOpen && isFirstInteraction) {
      this.hasWelcomed = true;

      this.messages.push({
        user: 'AI',
        text: '🤖 Typing...',
        timestamp: new Date()
      });
      this.scrollToBottom();

      setTimeout(() => {
        this.messages.pop();
        this.messages.push({
          user: 'AI',
          text: '👋 Welcome! How can I assist you today?',
          timestamp: new Date()
        });
        this.saveChatHistory();
        this.scrollToBottom();
      }, 800);
    }
  }


  askQuestion() {
    const trimmed = this.prompt.trim();
    if (!trimmed) return;

    this.messages.push({ user: 'User', text: trimmed, timestamp: new Date() });
    this.saveChatHistory();
    this.prompt = '';
    this.scrollToBottom();

    const thinkingIndex = this.messages.length;
    this.messages.push({ user: 'AI', text: '🤖 Typing...', timestamp: new Date() });
    this.scrollToBottom();

    this.chatService.sendPrompt(trimmed).subscribe({
      next: (res) => {
        this.messages[thinkingIndex] = {
          user: 'AI',
          text: res.response,
          timestamp: new Date()
        };
        this.tokens += res.tokens;
        this.saveChatHistory();
        this.scrollToBottom();
      },
      error: () => {
        this.messages[thinkingIndex] = {
          user: 'AI',
          text: '❌ Failed to respond',
          timestamp: new Date()
        };
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

  autoResize(event: Event) {
    const textarea = event.target as HTMLTextAreaElement;
    textarea.style.height = 'auto';

    const maxHeight = 200; // max height in pixels
    textarea.style.overflowY = 'hidden'; // prevent scroll while expanding

    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = `${newHeight}px`;

    // Enable scroll if content overflows max height
    if (textarea.scrollHeight > maxHeight) {
      textarea.style.overflowY = 'auto';
    }
  }

  scrollToBottom() {
    setTimeout(() => {
      const el = this.messageContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 0);
  }
}
