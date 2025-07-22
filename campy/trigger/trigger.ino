// Camera Sync - TTL triggering with Teensy board
// Inter-frame interval precision: ~ +/- 0.35 us
// Inter-frame interval accuracy: ~0.0035%
// Synchronicity: ~ 30 ns

// User-set parameters
uint32_t baudrate = 115200;

// Global variables
int DIG_out_pins[100];
int n_sync;
float frame_rate_in = 0;
float frame_rate_out = 0;
unsigned long frame_start, frame_period, time_zero;
uint32_t frame_count = 0;

void setup( void ) {

  Serial.begin(baudrate);
  delay(500);
  Serial.print("Set baudrate to ");
  Serial.print(baudrate);

  Serial.println("");
  Serial.print("Enter comma-separated string in this order: # dig pins, dig pin IDs, frame rate:");

  // Set DigPins using Python or Serial Monitor input
  n_sync = SetDigPins();

  // Set Frame Rate using Python or Serial Monitor input
  frame_rate_out = SetFrameRate();
  frame_period = SetFramePeriod(frame_rate_out);

  // Wait for streams and cams to initialize
  ResetTimer(); 
  
}


int SetDigPins() {
  
  // Receive Dig Pin array size from Python or Serial Monitor
  while (Serial.available() == 0) {}
  int num_pins = int( (unsigned int) Serial.parseFloat());

  // Print result and initialize array
  Serial.println("");
  Serial.print("Number of digital pins: ");
  Serial.print(num_pins);
  
  Serial.println("");
  Serial.print("Digital pins: ");
  
  for ( int i = 0; i < num_pins; i++ ) {
    // Receive digital pin IDs
    while (Serial.available() == 0) {}
    int input = int( (unsigned int) Serial.parseFloat());
    Serial.print(input);
    if (i+1 < num_pins) { Serial.print(","); }

    // Append pin number to array
    DIG_out_pins[i] = input;
  }

  // Set digital pins to OUTPUT mode and to LOW voltage
  for ( int i = 0; i < num_pins; i++ ) {
    pinMode(DIG_out_pins[i], OUTPUT);
    digitalWrite(DIG_out_pins[i], LOW);
  }

  return num_pins;
}


unsigned long SetFrameRate() {
  // Wait to receive frame rate from Python or Serial Monitor...
  while (Serial.available() == 0) {}
  frame_rate_in = Serial.parseFloat();

  // Output frame rate, avoid negative values
  if (frame_rate_in < 0) {
    frame_rate_out = 0;
  }
  else {
    frame_rate_out = frame_rate_in;
  }

  // Print results
  Serial.println("");
  Serial.print("Frame rate set to: ");
  Serial.print(frame_rate_out);
  Serial.print(" fps.");

  return frame_rate_out;
}


unsigned long SetFramePeriod( unsigned long fr ) {
  
  // Calculate frame period and pulse duration
  // Avoid divide-by-zero error
  if (fr == 0) {
    frame_period = 0xFFFFFFFF;
  }
  else {
    frame_period = 1e6 / fr;
  }

  Serial.println("");
  Serial.print("Frame period set to: ");
  Serial.print(frame_period);
  Serial.print(" microseconds.");

  return frame_period;
}


void FlushSerialBuffer() {
  
  while (Serial.available() != 0) {
    Serial.parseFloat();
  }
  
}


void ResetTimer() {
  
  delay(4000);
  FlushSerialBuffer();
  frame_count = 0;
  time_zero = frame_count * frame_period;
  frame_start = micros() + time_zero;
  
}


void SetPinsHigh() {
  
  // Disable interrupts to synchronize TTLs
  noInterrupts();
  for ( int i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], HIGH);
  }
  interrupts();
  
}


void SetPinsLow() {
  // Disable interrupts to synchronize TTLs
  noInterrupts();
  for ( int i = 0; i < n_sync; i++ ) {
    digitalWrite(DIG_out_pins[i], LOW);
  }
  interrupts();
}


unsigned long Timer() {
  
  return micros() + time_zero - frame_start;
}

void loop( void ) {
  
  if (Serial.available())
  {
    SetPinsLow();
    n_sync = SetDigPins();
    frame_rate_out = SetFrameRate();
    frame_period = SetFramePeriod(frame_rate_out);
    ResetTimer();
  }

  if (frame_rate_out > 0) {
    SetPinsLow();

    // Wait until end of this pulse period
    while (Timer() < frame_period / 2) {}

    SetPinsHigh();

    // Wait until end of this frame period
    while (Timer() < frame_period) {}

    frame_start = frame_start + frame_period;
  }
  
}
