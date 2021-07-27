// Camera Sync - TTL triggering with Teensy board
// Inter-frame interval precision: ~ +/- 1.5 us
// Inter-frame interval accuracy: ~ +40 ns
// Synchronicity: ~ ? ns (not tested yet)

// User-set parameters
int DIG_out_pins[] = {0,1,2,3,4,5};
uint32_t baudrate = 115200;

// Pre-allocated variables
int n_sync;
long frame_rate = 0;
unsigned long frame_period, pulse_duration;
unsigned long time_zero, pulse_end, frame_end;
int32_t frame_count = 0;


void setup( void ) {
  n_sync = int( sizeof(DIG_out_pins) / sizeof(int) );
  for ( byte i = 0; i < n_sync; i++ ) {
    pinMode(DIG_out_pins[i], OUTPUT);
    digitalWrite(DIG_out_pins[i], LOW);
  }
  
  Serial.begin(baudrate);
  Serial.println("Set baudrate to ");
  Serial.print(baudrate);
  Serial.println("Enter your frame rate:");
  
  // Wait to receive data from Python or Serial Monitor...
  while (Serial.available() == 0) {}

  frame_rate = Serial.parseInt();
  Serial.println(frame_rate);
  if (frame_rate == 0) { // Avoid divide-by-zero error
    frame_period = 0xFFFFFFFF;
    pulse_duration = 0xFFFFFFFF;
  }
  else {
    frame_period = 1e6 / frame_rate; // microseconds
    pulse_duration = frame_period / 2; // ~50% duty cycle
  }
  Serial.println(frame_period);
  Serial.println(pulse_duration);
  delay(4000); // Wait n ms for streams and cams to initialize
  time_zero = micros();
}


void loop( void ) {
  // Disable interrupts to synchronize TTLs
  noInterrupts();
  for ( byte i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], HIGH); 
  }
  interrupts();

  frame_count = frame_count + 1;
  pulse_end = frame_period * (frame_count - 1) + pulse_duration;
  frame_end = frame_period * frame_count;

  while ((micros() - time_zero) < pulse_end) {} // wait 

  // Disable interrupts to synchronize TTLs
  noInterrupts();
  for ( byte i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], LOW); 
  }
  interrupts();

  while ((micros() - time_zero) < frame_end) {} // wait
}
