// Camera Sync - TTL triggering with Teensy board
// Inter-frame interval precision: ~ +/- 1.5 us
// Inter-frame interval accuracy: ~ +40 ns
// Synchronicity: ~ ? ns (not tested yet)

// User-set parameters
int8_t DIG_out_pins[] = {0,1,2,3,4,5,6};
uint32_t baudrate = 115200;

// Global variables
int8_t n_sync;
float frame_rate_in = 0;
float frame_rate_out = 0;
unsigned long time_zero, frame_period, frame_end;
int32_t frame_count = 0;


void setup( void ) {
  n_sync = int8_t( sizeof(DIG_out_pins) / sizeof(int8_t) );
  for ( int8_t i = 0; i < n_sync; i++ ) {
    pinMode(DIG_out_pins[i], OUTPUT);
    digitalWrite(DIG_out_pins[i], LOW);
  }
  
  Serial.begin(baudrate);
  delay(500);
  Serial.print("Set baudrate to ");
  Serial.print(baudrate);
  Serial.println("");
  Serial.print("Enter your frame rate:");
  
  // Wait to receive data from Python or Serial Monitor...
  while (Serial.available() == 0) {}

  // Parse user input; output frame rate, period
  frame_rate_out = SetFrameRate();
  frame_period = SetFramePeriod(frame_rate_out);

  ResetTimer(); // Waits for streams and cams to initialize
}

unsigned long SetFrameRate() {
  frame_rate_in = Serial.parseFloat();

  // Output frame rate, avoid negative values
  if (frame_rate_in == 0) {}
  else if (frame_rate_in < 0) { frame_rate_out = 0; }
  else { frame_rate_out = frame_rate_in; }

  // Print results (make this a function)
  Serial.println("");
  Serial.print("Frame rate set to: ");
  Serial.print(frame_rate_out);
  Serial.print(" fps.");

  return frame_rate_out;
}

unsigned long SetFramePeriod( unsigned long fr ) {
  // Calculate frame period and pulse duration
  // Avoid divide-by-zero error
  if (fr == 0) { frame_period = 0xFFFFFFFF; }
  else { frame_period = 1e6 / fr; }
  
  Serial.println("");
  Serial.print("Frame period set to: ");
  Serial.print(frame_period);
  Serial.print(" microseconds.");

  return frame_period;
}

void FlushSerialBuffer() {
  while (Serial.available() != 0) {
    long floater = Serial.parseFloat();
  }
}

void ResetTimer() {
  delay(4000);
  FlushSerialBuffer();
  frame_count = 0;
  time_zero = micros();
}

void SetPinsHigh() {
  // Disable interrupts to synchronize TTLs
  noInterrupts();
  for ( int8_t i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], HIGH); 
  }
  interrupts();
}

void SetPinsLow() {
  // Disable interrupts to synchronize TTLs
  noInterrupts();
  for ( int8_t i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], LOW); 
  }
  interrupts();
}

void loop( void ) {
  if (Serial.available() != 0) 
  {
    SetPinsLow();
    frame_rate_out = SetFrameRate();
    frame_period = SetFramePeriod( frame_rate_out );
    ResetTimer();
  }

  if (frame_rate_out > 0) {
    SetPinsHigh();

    frame_count = frame_count + 1;
    frame_end = frame_period * frame_count;

    // Wait until end of this pulse period
    while ((micros() - time_zero) < frame_end - frame_period / 2) {} 
  
    SetPinsLow();

    // Wait until end of this frame period
    while ((micros() - time_zero) < frame_end) {} 
  }
}
