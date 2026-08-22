#import <Foundation/Foundation.h>

@protocol RSFarmController
- (NSDictionary *)submitBuild:(NSDictionary *)spec;
- (NSArray *)jobs;
- (NSArray *)workers;
- (BOOL)cancelJob:(NSString *)jobID;
- (BOOL)registerWorker:(NSString *)name capabilities:(NSDictionary *)capabilities;
- (BOOL)heartbeat:(NSString *)name;
- (NSDictionary *)nextJobForWorker:(NSString *)name;
- (BOOL)finishJob:(NSString *)jobID result:(NSDictionary *)result;
@end
